import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText
import os
import re
import json
import base64
import uuid

class VerilogModule:
    def __init__(self, name, filepath):
        self.name = name
        self.filepath = filepath
        self.ports = []
        self.parameters = []
        self.macros = {}
        
    def add_port(self, name, direction, dtype, width, dimensions=None):
        if dimensions is None:
            dimensions = []
        self.ports.append({
            'name': name,
            'direction': direction,
            'dtype': dtype,
            'width': width,
            'dimensions': dimensions  # For multi-dimensional ports
        })
        
    def add_parameter(self, name, value, ptype=None):
        self.parameters.append({
            'name': name,
            'value': value,
            'type': ptype
        })
        
    def add_macro(self, name, value):
        self.macros[name] = value
        
    def __str__(self):
        return f"{self.name} ({os.path.basename(self.filepath)})"

class ModuleInstance:
    def __init__(self, module_ref, instance_name):
        self.module_ref = module_ref
        self.instance_name = instance_name
        self.connections = {}  # port_name: (connection_type, signal_name)
        self.parameter_values = {}  # param_name: value
        
    def get_port_info(self, port_name):
        for port in self.module_ref.ports:
            if port['name'] == port_name:
                return port
        return None
        
    def get_parameter_info(self, param_name):
        for param in self.module_ref.parameters:
            if param['name'] == param_name:
                return param
        return None

class VerilogParser:
    @staticmethod
    def parse_verilog_file(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            raise ValueError(f"Error reading file: {str(e)}")
            
        # Preprocess: remove comments
        content = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        
        # Preprocess macros
        macros = {}
        macro_pattern = r"`define\s+(\w+)\s+(.+)"
        for match in re.finditer(macro_pattern, content):
            macro_name = match.group(1)
            macro_value = match.group(2).strip()
            macros[macro_name] = macro_value
            
        # Apply macros
        for macro, value in macros.items():
            content = content.replace(f"`{macro}", value)
            
        # Find module - more robust pattern
        module_pattern = r"module\s+(\w+)\s*(?:#\s*\(.*?\)\s*)?\s*\(?(.*?)\)?\s*;"
        module_match = re.search(module_pattern, content, re.DOTALL | re.IGNORECASE)
        if not module_match:
            return None
            
        module_name = module_match.group(1)
        module = VerilogModule(module_name, filepath)
        
        # Extract ports
        port_section = module_match.group(2)
        # Enhanced port pattern to capture various formats
        port_pattern = r"(input|output|inout)\s*(wire|logic|reg)?\s*(?:\[([^\]]*?)\])?\s*(\w+)"
        
        port_matches = []
        for match in re.finditer(port_pattern, port_section, re.IGNORECASE):
            port_matches.append(match)
            
        if not port_matches:
            # Try alternative pattern without direction
            port_pattern = r"(\w+)\s*(wire|logic|reg)?\s*(?:\[([^\]]*?)\])?\s*$"
            for match in re.finditer(port_pattern, port_section, re.IGNORECASE):
                port_matches.append(match)
        
        for match in port_matches:
            direction = match.group(1).lower() if match.group(1) else "wire"
            dtype = match.group(2).lower() if match.group(2) else "wire"
            width = match.group(3).strip() if match.group(3) else "1"
            name = match.group(4)
            module.add_port(name, direction, dtype, width)
            
        # Extract parameters - more robust pattern
        param_pattern = r"parameter\s+(?:type\s+)?\s*(\w+)\s*=\s*([^,;]+)"
        for match in re.finditer(param_pattern, content, re.IGNORECASE):
            name = match.group(1)
            value = match.group(2).strip()
            # Try to detect type
            ptype = None
            if re.match(r"^\d", value):
                ptype = "int"
            elif re.match(r"^[\"\']", value):
                ptype = "string"
            module.add_parameter(name, value, ptype)
            
        # Store macros
        for macro, value in macros.items():
            module.add_macro(macro, value)
            
        return module

class VerilogGenerator:
    @staticmethod
    def generate_top_module(instances, top_module_name):
        lines = []
        lines.append(f"// Auto-generated top module: {top_module_name}")
        lines.append(f"module {top_module_name} (")
        
        # Collect top-level ports (input/output)
        top_ports = []
        for instance in instances:
            for port_name, (conn_type, signal_name) in instance.connections.items():
                port_info = instance.get_port_info(port_name)
                if not port_info or not signal_name:
                    continue
                    
                direction = port_info['direction']
                width = port_info['width']
                
                # Format width: [width-1:0] or omit if width is 1
                width_str = ""
                if width != "1":
                    try:
                        # Try to parse width expression
                        if ':' in width:
                            # Already in [msb:lsb] format
                            width_str = f" [{width}]"
                        else:
                            # Convert to [width-1:0]
                            w_val = int(width)
                            if w_val > 1:
                                width_str = f" [{w_val-1}:0]"
                    except:
                        # If not a number, use as-is
                        if width != "1":
                            width_str = f" [{width}]"
                
                # Only create top-level ports for input/output connections
                if conn_type == "input" and direction == "input":
                    top_ports.append(f"input wire{width_str} {signal_name}")
                elif conn_type == "output" and direction == "output":
                    top_ports.append(f"output wire{width_str} {signal_name}")
        
        # Add top-level ports
        if top_ports:
            lines.append(",\n  ".join(top_ports))
        
        lines.append(");\n")
        
        # Wire declarations
        wires = {}
        for instance in instances:
            for port_name, (conn_type, signal_name) in instance.connections.items():
                port_info = instance.get_port_info(port_name)
                if not port_info or not signal_name:
                    continue
                    
                # Only create wires for wire connections
                if conn_type == "wire":
                    width = port_info['width']
                    
                    # Format width: [width-1:0] or omit if width is 1
                    width_str = ""
                    if width != "1":
                        try:
                            # Try to parse width expression
                            if ':' in width:
                                # Already in [msb:lsb] format
                                width_str = f" [{width}]"
                            else:
                                # Convert to [width-1:0]
                                w_val = int(width)
                                if w_val > 1:
                                    width_str = f" [{w_val-1}:0]"
                        except:
                            # If not a number, use as-is
                            if width != "1":
                                width_str = f" [{width}]"
                    
                    wires[signal_name] = width_str
        
        for signal_name, width_str in wires.items():
            lines.append(f"  wire{width_str} {signal_name};")
        if wires:
            lines.append("")
        
        # Module instances
        for instance in instances:
            lines.append(f"  // Source: {instance.module_ref.filepath}")
            param_strs = []
            for param in instance.module_ref.parameters:
                param_name = param['name']
                value = instance.parameter_values.get(param_name, param['value'])
                param_strs.append(f".{param_name}({value})")
            
            port_strs = []
            for port in instance.module_ref.ports:
                port_name = port['name']
                if port_name in instance.connections:
                    conn_type, signal_name = instance.connections[port_name]
                    port_strs.append(f".{port_name}({signal_name})")
                else:
                    port_strs.append(f".{port_name}()")
            
            param_conn = ""
            if param_strs:
                param_conn = " #(\n    " + ",\n    ".join(param_strs) + "\n  )"
            
            lines.append(f"  {instance.module_ref.name}{param_conn} {instance.instance_name} (")
            lines.append(",\n    ".join(port_strs))
            lines.append("  );\n")
        
        lines.append("endmodule")
        return "\n".join(lines)

class VerilogIntegrationTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Verilog Integration Tool")
        self.geometry("1000x700")
        
        self.modules = {}  # module_name: VerilogModule
        self.instances = []  # List of ModuleInstance
        self.current_instance = None
        self.drag_data = {"item": None}
        self.editing_cell = None
        
        self.setup_ui()
        self.setup_menus()
        
    def setup_ui(self):
        # Top button frame
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # First button group (Open and Save)
        btn_group1 = tk.Frame(top_frame)
        btn_group1.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_group1, text="Open Project", command=self.open_project).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_group1, text="Save Project", command=self.save_project).pack(side=tk.LEFT, padx=2)
        
        # Second button group (Open Module)
        btn_group2 = tk.Frame(top_frame)
        btn_group2.pack(side=tk.RIGHT, padx=5)
        
        tk.Button(btn_group2, text="Open Module", command=self.open_module).pack(side=tk.RIGHT, padx=2)
        
        # Main content frame
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Blue list (Modules)
        blue_frame = tk.LabelFrame(main_frame, text="Module Library", bg="#e0e8ff")
        blue_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        blue_frame.config(width=200)
        
        self.module_list = tk.Listbox(blue_frame, width=25, bg="#e0e8ff")
        self.module_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.module_list.bind("<Double-Button-1>", self.show_module_details)
        self.module_list.bind("<ButtonPress-1>", self.start_drag)
        self.module_list.bind("<B1-Motion>", self.drag_module)
        self.module_list.bind("<ButtonRelease-1>", self.drop_module)
        self.module_list.bind("<Button-3>", self.show_module_context_menu)
        
        # Yellow list (Instances)
        yellow_frame = tk.LabelFrame(main_frame, text="Instantiated Modules", bg="#fffacd")
        yellow_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        yellow_frame.config(width=200)
        
        self.instance_list = tk.Listbox(yellow_frame, width=25, bg="#fffacd")
        self.instance_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.instance_list.bind("<<ListboxSelect>>", self.select_instance)
        self.instance_list.bind("<ButtonRelease-1>", self.drop_module)
        self.instance_list.bind("<Button-3>", self.show_instance_context_menu)
        
        # Green list (Ports and Parameters)
        green_frame = tk.LabelFrame(main_frame, text="Ports and Parameters", bg="#e0ffe0")
        green_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create Treeview with columns
        self.port_tree = ttk.Treeview(green_frame, columns=("Property", "Connection", "Name"), show="headings")
        
        # Configure columns
        self.port_tree.column("Property", width=150, anchor=tk.W)
        self.port_tree.column("Connection", width=150, anchor=tk.W)
        self.port_tree.column("Name", width=150, anchor=tk.W)
        
        # Set headings
        self.port_tree.heading("Property", text="Property")
        self.port_tree.heading("Connection", text="Connection")
        self.port_tree.heading("Name", text="Name")
        
        self.port_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configure tags for different types
        self.port_tree.tag_configure('port', background='#f0f0f0')
        self.port_tree.tag_configure('parameter', background='#e0f0ff')
        
        # Create dropdown widgets
        self.connection_combobox = ttk.Combobox(self.port_tree)
        self.name_entry = ttk.Entry(self.port_tree)
        self.param_entry = ttk.Entry(self.port_tree)
        
        # Hide them initially
        self.connection_combobox.place_forget()
        self.name_entry.place_forget()
        self.param_entry.place_forget()
        
        # Bind events for editing
        self.port_tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.connection_combobox.bind("<<ComboboxSelected>>", self.on_connection_select)
        self.connection_combobox.bind("<Return>", self.on_connection_select)
        self.connection_combobox.bind("<FocusOut>", self.on_connection_select)
        self.name_entry.bind("<Return>", self.on_name_enter)
        self.name_entry.bind("<FocusOut>", self.on_name_enter)
        self.param_entry.bind("<Return>", self.on_param_enter)
        self.param_entry.bind("<FocusOut>", self.on_param_enter)
        
        # Bottom output frame
        output_frame = tk.LabelFrame(self, text="Output")
        output_frame.pack(fill=tk.BOTH, padx=5, pady=5)
        
        self.output_text = ScrolledText(output_frame, height=8)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)
        
    def setup_menus(self):
        # Module context menu
        self.module_context_menu = tk.Menu(self, tearoff=0)
        self.module_context_menu.add_command(label="Delete", command=self.delete_selected_module)
        self.module_context_menu.add_command(label="Refresh", command=self.refresh_selected_module)
        
        # Instance context menu
        self.instance_context_menu = tk.Menu(self, tearoff=0)
        self.instance_context_menu.add_command(label="Delete", command=self.delete_selected_instance)
        self.instance_context_menu.add_command(label="Rename", command=self.rename_selected_instance)
        
    def log(self, message):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)
        
    def open_module(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("Verilog Files", "*.v *.sv"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
            
        try:
            module = VerilogParser.parse_verilog_file(filepath)
            if module:
                self.modules[module.name] = module
                self.module_list.insert(tk.END, str(module))
                self.log(f"Successfully parsed module: {module.name}")
                self.log(f"  Ports: {[port['name'] for port in module.ports]}")
                self.log(f"  Parameters: {[param['name'] for param in module.parameters]}")
            else:
                self.log(f"Error: Could not parse module from {filepath}")
        except Exception as e:
            self.log(f"Error parsing file: {str(e)}")
            
    def show_module_details(self, event):
        selection = self.module_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)
        
        if not module:
            return
            
        # Create a new window to show module details
        detail_win = tk.Toplevel(self)
        detail_win.title(f"Module: {module.name}")
        detail_win.geometry("600x400")
        
        # Create a notebook for ports and parameters
        notebook = ttk.Notebook(detail_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Ports tab
        ports_frame = ttk.Frame(notebook)
        notebook.add(ports_frame, text="Ports")
        
        # Create Treeview for ports
        port_tree = ttk.Treeview(ports_frame, columns=("Name", "Direction", "Data Type", "Width"), show="headings")
        port_tree.column("Name", width=150, anchor=tk.W)
        port_tree.column("Direction", width=100, anchor=tk.W)
        port_tree.column("Data Type", width=100, anchor=tk.W)
        port_tree.column("Width", width=100, anchor=tk.W)
        port_tree.heading("Name", text="Name")
        port_tree.heading("Direction", text="Direction")
        port_tree.heading("Data Type", text="Data Type")
        port_tree.heading("Width", text="Width")
        port_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add ports to Treeview
        for port in module.ports:
            port_tree.insert("", tk.END, values=(
                port['name'],
                port['direction'],
                port['dtype'],
                port['width']
            ))
        
        # Parameters tab
        params_frame = ttk.Frame(notebook)
        notebook.add(params_frame, text="Parameters")
        
        # Create Treeview for parameters
        param_tree = ttk.Treeview(params_frame, columns=("Name", "Type", "Value"), show="headings")
        param_tree.column("Name", width=150, anchor=tk.W)
        param_tree.column("Type", width=100, anchor=tk.W)
        param_tree.column("Value", width=200, anchor=tk.W)
        param_tree.heading("Name", text="Name")
        param_tree.heading("Type", text="Type")
        param_tree.heading("Value", text="Value")
        param_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add parameters to Treeview
        for param in module.parameters:
            ptype = param['type'] if param['type'] else "value"
            param_tree.insert("", tk.END, values=(
                param['name'],
                ptype,
                param['value']
            ))
        
        # Macros tab
        macros_frame = ttk.Frame(notebook)
        notebook.add(macros_frame, text="Macros")
        
        # Create Treeview for macros
        macro_tree = ttk.Treeview(macros_frame, columns=("Name", "Value"), show="headings")
        macro_tree.column("Name", width=150, anchor=tk.W)
        macro_tree.column("Value", width=300, anchor=tk.W)
        macro_tree.heading("Name", text="Name")
        macro_tree.heading("Value", text="Value")
        macro_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add macros to Treeview
        for macro, value in module.macros.items():
            macro_tree.insert("", tk.END, values=(macro, value))
        
    def start_drag(self, event):
        selection = self.module_list.nearest(event.y)
        if selection >= 0:
            self.drag_data["item"] = selection
            self.module_list.selection_clear(0, tk.END)
            self.module_list.selection_set(selection)
            
    def drag_module(self, event):
        if self.drag_data["item"] is None:
            return
            
        # Check if we're over the instance list
        target_widget = self.instance_list.winfo_containing(event.x_root, event.y_root)
        if target_widget == self.instance_list:
            self.instance_list.config(bg="#ffffe0")  # Highlight
        else:
            self.instance_list.config(bg="#fffacd")  # Normal color
            
    def drop_module(self, event):
        if self.drag_data["item"] is None:
            return
            
        # Check if we're over the instance list
        target_widget = self.instance_list.winfo_containing(event.x_root, event.y_root)
        if target_widget == self.instance_list:
            index = self.drag_data["item"]
            module_name = self.module_list.get(index).split()[0]
            module = self.modules.get(module_name)
            
            if module:
                # Ask for instance name
                instance_name = simpledialog.askstring(
                    "Instance Name",
                    "Enter instance name:",
                    initialvalue=f"u_{module_name}"
                )
                
                if instance_name:
                    # Check if instance name already exists
                    if any(inst.instance_name == instance_name for inst in self.instances):
                        messagebox.showerror("Error", f"Instance name '{instance_name}' already exists!")
                    else:
                        # Create new instance
                        instance = ModuleInstance(module, instance_name)
                        self.instances.append(instance)
                        self.instance_list.insert(tk.END, instance_name)
                        self.log(f"Instantiated module: {module_name} as {instance_name}")
        
        # Reset drag data and background color
        self.instance_list.config(bg="#fffacd")
        self.drag_data = {"item": None}
        
    def select_instance(self, event):
        selection = self.instance_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        instance_name = self.instance_list.get(index)
        
        # Find the instance
        for instance in self.instances:
            if instance.instance_name == instance_name:
                self.current_instance = instance
                self.update_port_tree()
                return
                
    def update_port_tree(self):
        # Clear the tree
        for item in self.port_tree.get_children():
            self.port_tree.delete(item)
            
        if not self.current_instance:
            return
            
        # Add ports
        for port in self.current_instance.module_ref.ports:
            # Get connection info if exists
            conn_type = ""
            signal_name = ""
            if port['name'] in self.current_instance.connections:
                conn_type, signal_name = self.current_instance.connections[port['name']]
                
            self.port_tree.insert("", tk.END, values=(
                f"{port['name']} ({port['direction']} {port['dtype']} {port['width']})",
                conn_type,
                signal_name
            ), tags=('port',))
            
        # Add parameters
        for param in self.current_instance.module_ref.parameters:
            value = self.current_instance.parameter_values.get(
                param['name'], 
                param['value']
            )
            ptype = param['type'] if param['type'] else "value"
            self.port_tree.insert("", tk.END, values=(
                f"parameter {param['name']} ({ptype})",
                value,
                ""
            ), tags=('parameter',))
        
    def on_tree_click(self, event):
        # Get clicked region
        region = self.port_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
            
        # Get clicked item and column
        item = self.port_tree.identify_row(event.y)
        column = self.port_tree.identify_column(event.x)
        
        if not item or not column:
            return
            
        col_index = int(column[1:]) - 1
        current_value = self.port_tree.item(item, "values")[col_index]
        tags = self.port_tree.item(item, "tags")
        
        # Get cell coordinates
        x, y, width, height = self.port_tree.bbox(item, column)
        
        # Hide all editors first
        self.connection_combobox.place_forget()
        self.name_entry.place_forget()
        self.param_entry.place_forget()
        
        # Determine if it's a port or parameter
        is_port = 'port' in tags
        is_parameter = 'parameter' in tags
        
        if is_port:
            if col_index == 1:  # Connection column
                # Create dropdown with connection options
                options = ["input", "output", "wire"]
                self.connection_combobox.config(values=options)
                self.connection_combobox.set(current_value)
                self.connection_combobox.place(x=x, y=y, width=width, height=height)
                self.connection_combobox.focus_set()
                self.connection_combobox.selection_range(0, tk.END)
                self.editing_cell = (item, column, "connection")
                
            elif col_index == 2:  # Name column
                self.name_entry.delete(0, tk.END)
                self.name_entry.insert(0, current_value)
                self.name_entry.place(x=x, y=y, width=width, height=height)
                self.name_entry.focus_set()
                self.name_entry.selection_range(0, tk.END)
                self.editing_cell = (item, column, "name")
                
        elif is_parameter and col_index == 1:  # Parameter value
            self.param_entry.delete(0, tk.END)
            self.param_entry.insert(0, current_value)
            self.param_entry.place(x=x, y=y, width=width, height=height)
            self.param_entry.focus_set()
            self.param_entry.selection_range(0, tk.END)
            self.editing_cell = (item, column, "parameter")
            
    def on_connection_select(self, event=None):
        if not self.editing_cell or self.editing_cell[2] != "connection":
            return
            
        item, column, _ = self.editing_cell
        new_value = self.connection_combobox.get()
        
        # Update tree value
        values = list(self.port_tree.item(item, "values"))
        values[1] = new_value
        self.port_tree.item(item, values=values)
        
        # Update instance connection
        prop_name = values[0]
        port_name = prop_name.split()[0]  # Extract port name from property string
        
        # Preserve the signal name
        current_signal = self.current_instance.connections.get(port_name, ("", ""))[1]
        self.current_instance.connections[port_name] = (new_value, current_signal)
        
        # Hide combobox
        self.connection_combobox.place_forget()
        self.editing_cell = None
        
    def on_name_enter(self, event=None):
        if not self.editing_cell or self.editing_cell[2] != "name":
            return
            
        item, column, _ = self.editing_cell
        new_value = self.name_entry.get()
        
        # Update tree value
        values = list(self.port_tree.item(item, "values"))
        values[2] = new_value
        self.port_tree.item(item, values=values)
        
        # Update instance connection
        prop_name = values[0]
        port_name = prop_name.split()[0]  # Extract port name from property string
        
        # Preserve the connection type
        current_type = self.current_instance.connections.get(port_name, ("", ""))[0]
        self.current_instance.connections[port_name] = (current_type, new_value)
        
        # Hide entry
        self.name_entry.place_forget()
        self.editing_cell = None
        
    def on_param_enter(self, event=None):
        if not self.editing_cell or self.editing_cell[2] != "parameter":
            return
            
        item, column, _ = self.editing_cell
        new_value = self.param_entry.get()
        
        # Update tree value
        values = list(self.port_tree.item(item, "values"))
        values[1] = new_value
        self.port_tree.item(item, values=values)
        
        # Update instance parameter value
        prop_name = values[0]
        param_name = prop_name.split()[1]  # Extract parameter name from property string
        self.current_instance.parameter_values[param_name] = new_value
        
        # Hide entry
        self.param_entry.place_forget()
        self.editing_cell = None
        
    def show_module_context_menu(self, event):
        # Select the item under the cursor
        index = self.module_list.nearest(event.y)
        if index >= 0:
            self.module_list.selection_clear(0, tk.END)
            self.module_list.selection_set(index)
            self.module_list.activate(index)
            
            # Show context menu
            self.module_context_menu.post(event.x_root, event.y_root)
            
    def show_instance_context_menu(self, event):
        # Select the item under the cursor
        index = self.instance_list.nearest(event.y)
        if index >= 0:
            self.instance_list.selection_clear(0, tk.END)
            self.instance_list.selection_set(index)
            self.instance_list.activate(index)
            
            # Show context menu
            self.instance_context_menu.post(event.x_root, event.y_root)
            
    def delete_selected_module(self):
        selection = self.module_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)
        
        if not module:
            return
            
        # Check if any instances are using this module
        instances_using = [inst for inst in self.instances if inst.module_ref == module]
        if instances_using:
            messagebox.showerror("Error", 
                f"Cannot delete module '{module_name}' because it has {len(instances_using)} instances.\n"
                "Please delete the instances first.")
            return
            
        # Remove from module list
        del self.modules[module_name]
        self.module_list.delete(index)
        self.log(f"Deleted module: {module_name}")
        
    def refresh_selected_module(self):
        selection = self.module_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)
        
        if not module:
            return
            
        try:
            # Re-parse the module file
            new_module = VerilogParser.parse_verilog_file(module.filepath)
            if new_module:
                self.modules[module_name] = new_module
                self.log(f"Refreshed module: {module_name}")
                self.log(f"  Ports: {[port['name'] for port in new_module.ports]}")
                self.log(f"  Parameters: {[param['name'] for param in new_module.parameters]}")
            else:
                self.log(f"Error: Could not parse module from {module.filepath}")
        except Exception as e:
            self.log(f"Error refreshing module: {str(e)}")
            
    def delete_selected_instance(self):
        selection = self.instance_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        instance_name = self.instance_list.get(index)
        
        # Find the instance
        instance_to_delete = None
        for instance in self.instances:
            if instance.instance_name == instance_name:
                instance_to_delete = instance
                break
                
        if not instance_to_delete:
            return
            
        # Remove from instances list
        self.instances.remove(instance_to_delete)
        self.instance_list.delete(index)
        
        # If the current instance was deleted, clear the port tree
        if self.current_instance == instance_to_delete:
            self.current_instance = None
            for item in self.port_tree.get_children():
                self.port_tree.delete(item)
        
        self.log(f"Deleted instance: {instance_name}")
        
    def rename_selected_instance(self):
        selection = self.instance_list.curselection()
        if not selection:
            return
            
        index = selection[0]
        old_name = self.instance_list.get(index)
        
        # Find the instance
        instance_to_rename = None
        for instance in self.instances:
            if instance.instance_name == old_name:
                instance_to_rename = instance
                break
                
        if not instance_to_rename:
            return
            
        # Ask for new instance name
        new_name = simpledialog.askstring(
            "Rename Instance",
            "Enter new instance name:",
            initialvalue=old_name
        )
        
        if not new_name or new_name == old_name:
            return
            
        # Check if new name already exists
        if any(inst.instance_name == new_name for inst in self.instances):
            messagebox.showerror("Error", f"Instance name '{new_name}' already exists!")
            return
            
        # Update instance name
        instance_to_rename.instance_name = new_name
        self.instance_list.delete(index)
        self.instance_list.insert(index, new_name)
        self.instance_list.selection_set(index)
        
        self.log(f"Renamed instance: {old_name} -> {new_name}")
        
    def save_project(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".v",
            filetypes=[("Verilog Files", "*.v"), ("SystemVerilog Files", "*.sv"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
            
        # Generate top module name from filename
        top_name = os.path.basename(filepath).split('.')[0]
        
        # Generate Verilog code
        verilog_code = VerilogGenerator.generate_top_module(self.instances, top_name)
        
        # Add serialized data as comment
        serialized = self.serialize_data()
        encoded = base64.b64encode(serialized.encode()).decode()
        verilog_code += f"\n\n// VERILOG_TOOL_DATA: {encoded}"
        
        # Save to file
        with open(filepath, 'w') as f:
            f.write(verilog_code)
            
        self.log(f"Project saved to {filepath}")
        self.log(f"Top module '{top_name}' generated with {len(self.instances)} instances")
        
    def open_project(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("Verilog Files", "*.v *.sv"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
            
        try:
            with open(filepath, 'r') as f:
                content = f.read()
                
            # Find the serialized data
            match = re.search(r"// VERILOG_TOOL_DATA: (\S+)", content)
            if not match:
                self.log("Error: No tool data found in file")
                return
                
            encoded = match.group(1)
            serialized = base64.b64decode(encoded).decode()
            self.deserialize_data(serialized)
            
            self.log(f"Project loaded from {filepath}")
        except Exception as e:
            self.log(f"Error loading project: {str(e)}")
            
    def serialize_data(self):
        data = {
            "modules": {},
            "instances": []
        }
        
        # Serialize modules
        for name, module in self.modules.items():
            data["modules"][name] = {
                "filepath": module.filepath,
                "ports": module.ports,
                "parameters": module.parameters,
                "macros": module.macros
            }
            
        # Serialize instances
        for instance in self.instances:
            data["instances"].append({
                "module": instance.module_ref.name,
                "instance_name": instance.instance_name,
                "connections": instance.connections,
                "parameter_values": instance.parameter_values
            })
            
        return json.dumps(data)
        
    def deserialize_data(self, serialized):
        data = json.loads(serialized)
        
        # Clear current data
        self.modules = {}
        self.instances = []
        self.module_list.delete(0, tk.END)
        self.instance_list.delete(0, tk.END)
        
        # Recreate modules
        for name, mod_data in data["modules"].items():
            module = VerilogModule(name, mod_data["filepath"])
            module.ports = mod_data["ports"]
            module.parameters = mod_data["parameters"]
            module.macros = mod_data["macros"]
            self.modules[name] = module
            self.module_list.insert(tk.END, str(module))
            
        # Recreate instances
        for inst_data in data["instances"]:
            module = self.modules.get(inst_data["module"])
            if not module:
                continue
                
            instance = ModuleInstance(module, inst_data["instance_name"])
            
            # Restore connections
            instance.connections = inst_data["connections"]
                
            # Restore parameter values
            instance.parameter_values = inst_data["parameter_values"]
            
            self.instances.append(instance)
            self.instance_list.insert(tk.END, instance.instance_name)
            
        self.log(f"Loaded {len(self.modules)} modules and {len(self.instances)} instances")

if __name__ == "__main__":
    app = VerilogIntegrationTool()
    app.log("Verilog Integration Tool initialized. Use 'Open Module' to add Verilog modules.")
    app.log("Drag modules from the Module Library to the Instantiated Modules list.")
    app.mainloop()