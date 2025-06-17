import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText
import os
import re
import json
import base64
import uuid

# 定义 Verilog 模块类，用于存储解析后的 Verilog 模块信息
class VerilogModule:
    def __init__(self, name, filepath):
        """
        初始化 Verilog 模块对象。

        :param name: 模块的名称
        :param filepath: 模块所在文件的路径
        """
        self.name = name
        self.filepath = filepath
        self.ports = []  # 存储模块端口信息的列表
        self.parameters = []  # 存储模块参数信息的列表
        self.macros = {}  # 存储模块宏定义的字典

    def add_port(self, name, direction, dtype, width, dimensions=None):
        """
        向模块中添加端口信息。

        :param name: 端口名称
        :param direction: 端口方向（input/output/inout）
        :param dtype: 端口数据类型
        :param width: 端口位宽
        :param dimensions: 端口多维信息，默认为空列表
        """
        if dimensions is None:
            dimensions = []
        self.ports.append({
            'name': name,
            'direction': direction,
            'dtype': dtype,
            'width': width,
            'dimensions': dimensions  # 用于多维端口
        })

    def add_parameter(self, name, value, ptype=None):
        """
        向模块中添加参数信息。

        :param name: 参数名称
        :param value: 参数值
        :param ptype: 参数类型，默认为 None
        """
        self.parameters.append({
            'name': name,
            'value': value,
            'type': ptype
        })

    def add_macro(self, name, value):
        """
        向模块中添加宏定义。

        :param name: 宏名称
        :param value: 宏的值
        """
        self.macros[name] = value

    def __str__(self):
        """
        返回模块名称和所在文件名的字符串表示。

        :return: 格式化后的字符串
        """
        return f"{self.name} ({os.path.basename(self.filepath)})"

# 定义模块实例类，用于表示 Verilog 模块的实例
class ModuleInstance:
    def __init__(self, module_ref, instance_name):
        """
        初始化模块实例对象。

        :param module_ref: 模块引用，指向 VerilogModule 对象
        :param instance_name: 实例名称
        """
        self.module_ref = module_ref
        self.instance_name = instance_name
        self.connections = {}  # 端口连接信息，键为端口名，值为 (连接类型, 信号名)
        self.parameter_values = {}  # 参数值信息，键为参数名，值为参数值

    def get_port_info(self, port_name):
        """
        根据端口名获取端口信息。

        :param port_name: 端口名称
        :return: 端口信息字典，如果未找到则返回 None
        """
        for port in self.module_ref.ports:
            if port['name'] == port_name:
                return port
        return None

    def get_parameter_info(self, param_name):
        """
        根据参数名获取参数信息。

        :param param_name: 参数名称
        :return: 参数信息字典，如果未找到则返回 None
        """
        for param in self.module_ref.parameters:
            if param['name'] == param_name:
                return param
        return None

# 定义 Verilog 文件解析器类，用于解析 Verilog 文件
class VerilogParser:
    @staticmethod
    def parse_verilog_file(filepath):
        """
        解析 Verilog 文件，提取模块、端口、参数和宏信息。

        :param filepath: Verilog 文件路径
        :return: VerilogModule 对象，如果解析失败则返回 None
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            raise ValueError(f"Error reading file: {str(e)}")

        # 预处理：移除注释
        content = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

        # 预处理宏
        macros = {}
        macro_pattern = r"`define\s+(\w+)\s+(.+)"
        for match in re.finditer(macro_pattern, content):
            macro_name = match.group(1)
            macro_value = match.group(2).strip()
            macros[macro_name] = macro_value

        # 应用宏
        for macro, value in macros.items():
            content = content.replace(f"`{macro}", value)

        # 查找模块 - 更健壮的正则表达式
        module_pattern = r"module\s+(\w+)\s*(?:#\s*\(.*?\)\s*)?\s*\(?(.*?)\)?\s*;"
        module_match = re.search(module_pattern, content, re.DOTALL | re.IGNORECASE)
        if not module_match:
            return None

        module_name = module_match.group(1)
        module = VerilogModule(module_name, filepath)

        # 提取端口
        port_section = module_match.group(2)
        # 增强的端口正则表达式，用于捕获各种格式的端口
        port_pattern = r"(input|output|inout)\s*(wire|logic|reg)?\s*(?:\[([^\]]*?)\])?\s*(\w+)"

        port_matches = []
        for match in re.finditer(port_pattern, port_section, re.IGNORECASE):
            port_matches.append(match)

        if not port_matches:
            # 尝试无方向的替代正则表达式
            port_pattern = r"(\w+)\s*(wire|logic|reg)?\s*(?:\[([^\]]*?)\])?\s*$"
            for match in re.finditer(port_pattern, port_section, re.IGNORECASE):
                port_matches.append(match)

        for match in port_matches:
            direction = match.group(1).lower() if match.group(1) else "wire"
            dtype = match.group(2).lower() if match.group(2) else "wire"
            width = match.group(3).strip() if match.group(3) else "1"
            name = match.group(4)
            module.add_port(name, direction, dtype, width)

        # 提取参数 - 更健壮的正则表达式
        param_pattern = r"parameter\s+(?:type\s+)?\s*(\w+)\s*=\s*([^,;]+)"
        for match in re.finditer(param_pattern, content, re.IGNORECASE):
            name = match.group(1)
            value = match.group(2).strip()
            # 尝试检测类型
            ptype = None
            if re.match(r"^\d", value):
                ptype = "int"
            elif re.match(r"^[\"\']", value):
                ptype = "string"
            module.add_parameter(name, value, ptype)

        # 存储宏
        for macro, value in macros.items():
            module.add_macro(macro, value)

        return module

# 定义 Verilog 代码生成器类，用于生成顶层模块的 Verilog 代码
class VerilogGenerator:
    @staticmethod
    def generate_top_module(instances, top_module_name):
        """
        根据模块实例列表生成顶层模块的 Verilog 代码。

        :param instances: 模块实例列表
        :param top_module_name: 顶层模块名称
        :return: 生成的 Verilog 代码字符串
        """
        lines = []
        lines.append(f"// Auto-generated top module: {top_module_name}")
        lines.append(f"module {top_module_name} (")

        # 收集顶层端口（input/output）
        top_ports = []
        for instance in instances:
            for port_name, (conn_type, signal_name) in instance.connections.items():
                port_info = instance.get_port_info(port_name)
                if not port_info or not signal_name:
                    continue

                direction = port_info['direction']
                width = port_info['width']

                # 格式化位宽：[width-1:0]，如果位宽为 1 则省略
                width_str = ""
                if width != "1":
                    try:
                        # 尝试解析位宽表达式
                        if ':' in width:
                            # 已经是 [msb:lsb] 格式
                            width_str = f" [{width}]"
                        else:
                            # 转换为 [width-1:0]
                            w_val = int(width)
                            if w_val > 1:
                                width_str = f" [{w_val-1}:0]"
                    except:
                        # 如果不是数字，原样使用
                        if width != "1":
                            width_str = f" [{width}]"

                # 仅为 input/output 连接创建顶层端口
                if conn_type == "input" and direction == "input":
                    top_ports.append(f"input wire{width_str} {signal_name}")
                elif conn_type == "output" and direction == "output":
                    top_ports.append(f"output wire{width_str} {signal_name}")

        # 添加顶层端口
        if top_ports:
            lines.append(",\n  ".join(top_ports))

        lines.append(");\n")

        # 线网声明
        wires = {}
        for instance in instances:
            for port_name, (conn_type, signal_name) in instance.connections.items():
                port_info = instance.get_port_info(port_name)
                if not port_info or not signal_name:
                    continue

                # 仅为 wire 连接创建线网
                if conn_type == "wire":
                    width = port_info['width']

                    # 格式化位宽：[width-1:0]，如果位宽为 1 则省略
                    width_str = ""
                    if width != "1":
                        try:
                            # 尝试解析位宽表达式
                            if ':' in width:
                                # 已经是 [msb:lsb] 格式
                                width_str = f" [{width}]"
                            else:
                                # 转换为 [width-1:0]
                                w_val = int(width)
                                if w_val > 1:
                                    width_str = f" [{w_val-1}:0]"
                        except:
                            # 如果不是数字，原样使用
                            if width != "1":
                                width_str = f" [{width}]"

                    wires[signal_name] = width_str

        for signal_name, width_str in wires.items():
            lines.append(f"  wire{width_str} {signal_name};")
        if wires:
            lines.append("")

        # 模块实例化
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

# 定义 Verilog 集成工具类，继承自 tkinter.Tk，用于创建 GUI 应用
class VerilogIntegrationTool(tk.Tk):
    def __init__(self):
        """
        初始化 Verilog 集成工具应用。
        """
        super().__init__()
        self.title("Verilog Integration Tool")
        self.geometry("1000x700")

        self.modules = {}  # 存储模块信息，键为模块名，值为 VerilogModule 对象
        self.instances = []  # 存储模块实例列表
        self.current_instance = None  # 当前选中的模块实例
        self.drag_data = {"item": None}  # 拖拽数据
        self.editing_cell = None  # 当前正在编辑的表格单元格

        self.setup_ui()  # 初始化 UI
        self.setup_menus()  # 初始化菜单

    def setup_ui(self):
        """
        设置应用的用户界面。
        """
        # 顶部按钮框架
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        # 第一组按钮（打开项目和保存项目）
        btn_group1 = tk.Frame(top_frame)
        btn_group1.pack(side=tk.LEFT, padx=5)

        tk.Button(btn_group1, text="Open Project", command=self.open_project).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_group1, text="Save Project", command=self.save_project).pack(side=tk.LEFT, padx=2)

        # 第二组按钮（打开模块）
        btn_group2 = tk.Frame(top_frame)
        btn_group2.pack(side=tk.RIGHT, padx=5)

        tk.Button(btn_group2, text="Open Module", command=self.open_module).pack(side=tk.RIGHT, padx=2)

        # 主内容框架
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 蓝色列表（模块库）
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

        # 黄色列表（实例化模块）
        yellow_frame = tk.LabelFrame(main_frame, text="Instantiated Modules", bg="#fffacd")
        yellow_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        yellow_frame.config(width=200)

        self.instance_list = tk.Listbox(yellow_frame, width=25, bg="#fffacd")
        self.instance_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.instance_list.bind("<<ListboxSelect>>", self.select_instance)
        self.instance_list.bind("<ButtonRelease-1>", self.drop_module)
        self.instance_list.bind("<Button-3>", self.show_instance_context_menu)

        # 绿色列表（端口和参数）
        green_frame = tk.LabelFrame(main_frame, text="Ports and Parameters", bg="#e0ffe0")
        green_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建 Treeview 表格，用于显示端口和参数信息
        self.port_tree = ttk.Treeview(green_frame, columns=("Property", "Connection", "Name"), show="headings")

        # 配置列
        self.port_tree.column("Property", width=150, anchor=tk.W)
        self.port_tree.column("Connection", width=150, anchor=tk.W)
        self.port_tree.column("Name", width=150, anchor=tk.W)

        # 设置表头
        self.port_tree.heading("Property", text="Property")
        self.port_tree.heading("Connection", text="Connection")
        self.port_tree.heading("Name", text="Name")

        self.port_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 配置不同类型的标签样式
        self.port_tree.tag_configure('port', background='#f0f0f0')
        self.port_tree.tag_configure('parameter', background='#e0f0ff')

        # 创建下拉框和输入框控件
        self.connection_combobox = ttk.Combobox(self.port_tree)
        self.name_entry = ttk.Entry(self.port_tree)
        self.param_entry = ttk.Entry(self.port_tree)

        # 初始隐藏这些控件
        self.connection_combobox.place_forget()
        self.name_entry.place_forget()
        self.param_entry.place_forget()

        # 绑定编辑事件
        self.port_tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.connection_combobox.bind("<<ComboboxSelected>>", self.on_connection_select)
        self.connection_combobox.bind("<Return>", self.on_connection_select)
        self.connection_combobox.bind("<FocusOut>", self.on_connection_select)
        self.name_entry.bind("<Return>", self.on_name_enter)
        self.name_entry.bind("<FocusOut>", self.on_name_enter)
        self.param_entry.bind("<Return>", self.on_param_enter)
        self.param_entry.bind("<FocusOut>", self.on_param_enter)

        # 底部输出框架
        output_frame = tk.LabelFrame(self, text="Output")
        output_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        self.output_text = ScrolledText(output_frame, height=8)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)

    def setup_menus(self):
        """
        设置上下文菜单。
        """
        # 模块上下文菜单
        self.module_context_menu = tk.Menu(self, tearoff=0)
        self.module_context_menu.add_command(label="Delete", command=self.delete_selected_module)
        self.module_context_menu.add_command(label="Refresh", command=self.refresh_selected_module)

        # 实例上下文菜单
        self.instance_context_menu = tk.Menu(self, tearoff=0)
        self.instance_context_menu.add_command(label="Delete", command=self.delete_selected_instance)
        self.instance_context_menu.add_command(label="Rename", command=self.rename_selected_instance)

    def log(self, message):
        """
        在输出框中记录日志信息。

        :param message: 要记录的日志消息
        """
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)

    def open_module(self):
        """
        打开 Verilog 文件并解析模块信息。
        """
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
        """
        显示模块的详细信息，包括端口、参数和宏。

        :param event: 鼠标双击事件
        """
        selection = self.module_list.curselection()
        if not selection:
            return

        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)

        if not module:
            return

        # 创建新窗口显示模块详细信息
        detail_win = tk.Toplevel(self)
        detail_win.title(f"Module: {module.name}")
        detail_win.geometry("600x400")

        # 创建笔记本控件，用于切换不同信息页
        notebook = ttk.Notebook(detail_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 端口标签页
        ports_frame = ttk.Frame(notebook)
        notebook.add(ports_frame, text="Ports")

        # 创建 Treeview 表格显示端口信息
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

        # 向 Treeview 表格添加端口信息
        for port in module.ports:
            port_tree.insert("", tk.END, values=(
                port['name'],
                port['direction'],
                port['dtype'],
                port['width']
            ))

        # 参数标签页
        params_frame = ttk.Frame(notebook)
        notebook.add(params_frame, text="Parameters")

        # 创建 Treeview 表格显示参数信息
        param_tree = ttk.Treeview(params_frame, columns=("Name", "Type", "Value"), show="headings")
        param_tree.column("Name", width=150, anchor=tk.W)
        param_tree.column("Type", width=100, anchor=tk.W)
        param_tree.column("Value", width=200, anchor=tk.W)
        param_tree.heading("Name", text="Name")
        param_tree.heading("Type", text="Type")
        param_tree.heading("Value", text="Value")
        param_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 向 Treeview 表格添加参数信息
        for param in module.parameters:
            ptype = param['type'] if param['type'] else "value"
            param_tree.insert("", tk.END, values=(
                param['name'],
                ptype,
                param['value']
            ))

        # 宏标签页
        macros_frame = ttk.Frame(notebook)
        notebook.add(macros_frame, text="Macros")

        # 创建 Treeview 表格显示宏信息
        macro_tree = ttk.Treeview(macros_frame, columns=("Name", "Value"), show="headings")
        macro_tree.column("Name", width=150, anchor=tk.W)
        macro_tree.column("Value", width=300, anchor=tk.W)
        macro_tree.heading("Name", text="Name")
        macro_tree.heading("Value", text="Value")
        macro_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 向 Treeview 表格添加宏信息
        for macro, value in module.macros.items():
            macro_tree.insert("", tk.END, values=(macro, value))

    def start_drag(self, event):
        """
        开始拖拽模块操作。

        :param event: 鼠标按下事件
        """
        selection = self.module_list.nearest(event.y)
        if selection >= 0:
            self.drag_data["item"] = selection
            self.module_list.selection_clear(0, tk.END)
            self.module_list.selection_set(selection)

    def drag_module(self, event):
        """
        拖拽模块过程中的操作，根据鼠标位置高亮实例列表。

        :param event: 鼠标移动事件
        """
        if self.drag_data["item"] is None:
            return

        # 检查是否在实例列表上方
        target_widget = self.instance_list.winfo_containing(event.x_root, event.y_root)
        if target_widget == self.instance_list:
            self.instance_list.config(bg="#ffffe0")  # 高亮显示
        else:
            self.instance_list.config(bg="#fffacd")  # 恢复正常颜色

    def drop_module(self, event):
        """
        释放鼠标完成模块拖拽操作，创建新的模块实例。

        :param event: 鼠标释放事件
        """
        if self.drag_data["item"] is None:
            return

        # 检查是否在实例列表上方
        target_widget = self.instance_list.winfo_containing(event.x_root, event.y_root)
        if target_widget == self.instance_list:
            index = self.drag_data["item"]
            module_name = self.module_list.get(index).split()[0]
            module = self.modules.get(module_name)

            if module:
                # 询问实例名称
                instance_name = simpledialog.askstring(
                    "Instance Name",
                    "Enter instance name:",
                    initialvalue=f"u_{module_name}"
                )

                if instance_name:
                    # 检查实例名称是否已存在
                    if any(inst.instance_name == instance_name for inst in self.instances):
                        messagebox.showerror("Error", f"Instance name '{instance_name}' already exists!")
                    else:
                        # 创建新实例
                        instance = ModuleInstance(module, instance_name)
                        self.instances.append(instance)
                        self.instance_list.insert(tk.END, instance_name)
                        self.log(f"Instantiated module: {module_name} as {instance_name}")

        # 重置拖拽数据和背景颜色
        self.instance_list.config(bg="#fffacd")
        self.drag_data = {"item": None}

    def select_instance(self, event):
        """
        选择实例时更新端口和参数表格。

        :param event: 列表框选择事件
        """
        selection = self.instance_list.curselection()
        if not selection:
            return

        index = selection[0]
        instance_name = self.instance_list.get(index)

        # 查找实例
        for instance in self.instances:
            if instance.instance_name == instance_name:
                self.current_instance = instance
                self.update_port_tree()
                return

    def update_port_tree(self):
        """
        更新端口和参数表格的显示内容。
        """
        # 清空表格
        for item in self.port_tree.get_children():
            self.port_tree.delete(item)

        if not self.current_instance:
            return

        # 添加端口信息
        for port in self.current_instance.module_ref.ports:
            # 获取连接信息（如果存在）
            conn_type = ""
            signal_name = ""
            if port['name'] in self.current_instance.connections:
                conn_type, signal_name = self.current_instance.connections[port['name']]

            self.port_tree.insert("", tk.END, values=(
                f"{port['name']} ({port['direction']} {port['dtype']} {port['width']})",
                conn_type,
                signal_name
            ), tags=('port',))

        # 添加参数信息
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
        """
        点击端口和参数表格时，根据点击位置显示编辑控件。

        :param event: 鼠标点击事件
        """
        # 获取点击区域
        region = self.port_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        # 获取点击的表格项和列
        item = self.port_tree.identify_row(event.y)
        column = self.port_tree.identify_column(event.x)

        if not item or not column:
            return

        col_index = int(column[1:]) - 1
        current_value = self.port_tree.item(item, "values")[col_index]
        tags = self.port_tree.item(item, "tags")

        # 获取单元格坐标
        x, y, width, height = self.port_tree.bbox(item, column)

        # 先隐藏所有编辑控件
        self.connection_combobox.place_forget()
        self.name_entry.place_forget()
        self.param_entry.place_forget()

        # 判断是端口还是参数
        is_port = 'port' in tags
        is_parameter = 'parameter' in tags

        if is_port:
            if col_index == 1:  # 连接类型列
                # 创建下拉框显示连接选项
                options = ["input", "output", "wire"]
                self.connection_combobox.config(values=options)
                self.connection_combobox.set(current_value)
                self.connection_combobox.place(x=x, y=y, width=width, height=height)
                self.connection_combobox.focus_set()
                self.connection_combobox.selection_range(0, tk.END)
                self.editing_cell = (item, column, "connection")

            elif col_index == 2:  # 信号名称列
                self.name_entry.delete(0, tk.END)
                self.name_entry.insert(0, current_value)
                self.name_entry.place(x=x, y=y, width=width, height=height)
                self.name_entry.focus_set()
                self.name_entry.selection_range(0, tk.END)
                self.editing_cell = (item, column, "name")

        elif is_parameter and col_index == 1:  # 参数值列
            self.param_entry.delete(0, tk.END)
            self.param_entry.insert(0, current_value)
            self.param_entry.place(x=x, y=y, width=width, height=height)
            self.param_entry.focus_set()
            self.param_entry.selection_range(0, tk.END)
            self.editing_cell = (item, column, "parameter")

    def on_connection_select(self, event=None):
        """
        选择连接类型后更新表格和实例连接信息。

        :param event: 下拉框选择事件
        """
        if not self.editing_cell or self.editing_cell[2] != "connection":
            return

        item, column, _ = self.editing_cell
        new_value = self.connection_combobox.get()

        # 更新表格值
        values = list(self.port_tree.item(item, "values"))
        values[1] = new_value
        self.port_tree.item(item, values=values)

        # 更新实例连接信息
        prop_name = values[0]
        port_name = prop_name.split()[0]  # 从属性字符串中提取端口名

        # 保留信号名称
        current_signal = self.current_instance.connections.get(port_name, ("", ""))[1]
        self.current_instance.connections[port_name] = (new_value, current_signal)

        # 隐藏下拉框
        self.connection_combobox.place_forget()
        self.editing_cell = None

    def on_name_enter(self, event=None):
        """
        输入信号名称后更新表格和实例连接信息。

        :param event: 输入框回车或失去焦点事件
        """
        if not self.editing_cell or self.editing_cell[2] != "name":
            return

        item, column, _ = self.editing_cell
        new_value = self.name_entry.get()

        # 更新表格值
        values = list(self.port_tree.item(item, "values"))
        values[2] = new_value
        self.port_tree.item(item, values=values)

        # 更新实例连接信息
        prop_name = values[0]
        port_name = prop_name.split()[0]  # 从属性字符串中提取端口名

        # 保留连接类型
        current_type = self.current_instance.connections.get(port_name, ("", ""))[0]
        self.current_instance.connections[port_name] = (current_type, new_value)

        # 隐藏输入框
        self.name_entry.place_forget()
        self.editing_cell = None

    def on_param_enter(self, event=None):
        """
        输入参数值后更新表格和实例参数信息。

        :param event: 输入框回车或失去焦点事件
        """
        if not self.editing_cell or self.editing_cell[2] != "parameter":
            return

        item, column, _ = self.editing_cell
        new_value = self.param_entry.get()

        # 更新表格值
        values = list(self.port_tree.item(item, "values"))
        values[1] = new_value
        self.port_tree.item(item, values=values)

        # 更新实例参数值
        prop_name = values[0]
        param_name = prop_name.split()[1]  # 从属性字符串中提取参数名
        self.current_instance.parameter_values[param_name] = new_value

        # 隐藏输入框
        self.param_entry.place_forget()
        self.editing_cell = None

    def show_module_context_menu(self, event):
        """
        显示模块列表的上下文菜单。

        :param event: 鼠标右键点击事件
        """
        # 选择鼠标光标下的项
        index = self.module_list.nearest(event.y)
        if index >= 0:
            self.module_list.selection_clear(0, tk.END)
            self.module_list.selection_set(index)
            self.module_list.activate(index)

            # 显示上下文菜单
            self.module_context_menu.post(event.x_root, event.y_root)

    def show_instance_context_menu(self, event):
        """
        显示实例列表的上下文菜单。

        :param event: 鼠标右键点击事件
        """
        # 选择鼠标光标下的项
        index = self.instance_list.nearest(event.y)
        if index >= 0:
            self.instance_list.selection_clear(0, tk.END)
            self.instance_list.selection_set(index)
            self.instance_list.activate(index)

            # 显示上下文菜单
            self.instance_context_menu.post(event.x_root, event.y_root)

    def delete_selected_module(self):
        """
        删除选中的模块，如果有实例使用该模块则提示错误。
        """
        selection = self.module_list.curselection()
        if not selection:
            return

        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)

        if not module:
            return

        # 检查是否有实例使用该模块
        instances_using = [inst for inst in self.instances if inst.module_ref == module]
        if instances_using:
            messagebox.showerror("Error",
                f"Cannot delete module '{module_name}' because it has {len(instances_using)} instances.\n"
                "Please delete the instances first.")
            return

        # 从模块列表中移除
        del self.modules[module_name]
        self.module_list.delete(index)
        self.log(f"Deleted module: {module_name}")

    def refresh_selected_module(self):
        """
        刷新选中的模块，重新解析模块文件。
        """
        selection = self.module_list.curselection()
        if not selection:
            return

        index = selection[0]
        module_name = self.module_list.get(index).split()[0]
        module = self.modules.get(module_name)

        if not module:
            return

        try:
            # 重新解析模块文件
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
        """
        删除选中的模块实例。
        """
        selection = self.instance_list.curselection()
        if not selection:
            return

        index = selection[0]
        instance_name = self.instance_list.get(index)

        # 查找要删除的实例
        instance_to_delete = None
        for instance in self.instances:
            if instance.instance_name == instance_name:
                instance_to_delete = instance
                break

        if not instance_to_delete:
            return

        # 从实例列表中移除
        self.instances.remove(instance_to_delete)
        self.instance_list.delete(index)

        # 如果当前实例被删除，清空端口表格
        if self.current_instance == instance_to_delete:
            self.current_instance = None
            for item in self.port_tree.get_children():
                self.port_tree.delete(item)

        self.log(f"Deleted instance: {instance_name}")

    def rename_selected_instance(self):
        """
        重命名选中的模块实例。
        """
        selection = self.instance_list.curselection()
        if not selection:
            return

        index = selection[0]
        old_name = self.instance_list.get(index)

        # 查找要重命名的实例
        instance_to_rename = None
        for instance in self.instances:
            if instance.instance_name == old_name:
                instance_to_rename = instance
                break

        if not instance_to_rename:
            return

        # 询问新的实例名称
        new_name = simpledialog.askstring(
            "Rename Instance",
            "Enter new instance name:",
            initialvalue=old_name
        )

        if not new_name or new_name == old_name:
            return

        # 检查新名称是否已存在
        if any(inst.instance_name == new_name for inst in self.instances):
            messagebox.showerror("Error", f"Instance name '{new_name}' already exists!")
            return

        # 更新实例名称
        instance_to_rename.instance_name = new_name
        self.instance_list.delete(index)
        self.instance_list.insert(index, new_name)
        self.instance_list.selection_set(index)

        self.log(f"Renamed instance: {old_name} -> {new_name}")

    def save_project(self):
        """
        保存项目，生成顶层模块的 Verilog 代码并保存到文件。
        """
        filepath = filedialog.asksaveasfilename(
            defaultextension=".v",
            filetypes=[("Verilog Files", "*.v"), ("SystemVerilog Files", "*.sv"), ("All Files", "*.*")]
        )

        if not filepath:
            return

        # 从文件名生成顶层模块名称
        top_name = os.path.basename(filepath).split('.')[0]

        # 生成 Verilog 代码
        verilog_code = VerilogGenerator.generate_top_module(self.instances, top_name)

        # 添加序列化数据作为注释
        serialized = self.serialize_data()
        encoded = base64.b64encode(serialized.encode()).decode()
        verilog_code += f"\n\n// VERILOG_TOOL_DATA: {encoded}"

        # 保存到文件
        with open(filepath, 'w') as f:
            f.write(verilog_code)

        self.log(f"Project saved to {filepath}")
        self.log(f"Top module '{top_name}' generated with {len(self.instances)} instances")

    def open_project(self):
        """
        打开项目，从文件中读取序列化数据并恢复项目状态。
        """
        filepath = filedialog.askopenfilename(
            filetypes=[("Verilog Files", "*.v *.sv"), ("All Files", "*.*")]
        )

        if not filepath:
            return

        try:
            with open(filepath, 'r') as f:
                content = f.read()

            # 查找序列化数据
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
        """
        序列化项目数据，将模块和实例信息转换为 JSON 字符串。

        :return: 序列化后的 JSON 字符串
        """
        data = {
            "modules": {},
            "instances": []
        }

        # 序列化模块信息
        for name, module in self.modules.items():
            data["modules"][name] = {
                "filepath": module.filepath,
                "ports": module.ports,
                "parameters": module.parameters,
                "macros": module.macros
            }

        # 序列化实例信息
        for instance in self.instances:
            data["instances"].append({
                "module": instance.module_ref.name,
                "instance_name": instance.instance_name,
                "connections": instance.connections,
                "parameter_values": instance.parameter_values
            })

        return json.dumps(data)

    def deserialize_data(self, serialized):
        """
        反序列化项目数据，从 JSON 字符串恢复模块和实例信息。

        :param serialized: 序列化后的 JSON 字符串
        """
        data = json.loads(serialized)

        # 清空当前数据
        self.modules = {}
        self.instances = []
        self.module_list.delete(0, tk.END)
        self.instance_list.delete(0, tk.END)

        # 重新创建模块
        for name, mod_data in data["modules"].items():
            module = VerilogModule(name, mod_data["filepath"])
            module.ports = mod_data["ports"]
            module.parameters = mod_data["parameters"]
            module.macros = mod_data["macros"]
            self.modules[name] = module
            self.module_list.insert(tk.END, str(module))

        # 重新创建实例
        for inst_data in data["instances"]:
            module = self.modules.get(inst_data["module"])
            if not module:
                continue

            instance = ModuleInstance(module, inst_data["instance_name"])

            # 恢复连接信息
            instance.connections = inst_data["connections"]

            # 恢复参数值
            instance.parameter_values = inst_data["parameter_values"]

            self.instances.append(instance)
            self.instance_list.insert(tk.END, instance.instance_name)

        self.log(f"Loaded {len(self.modules)} modules and {len(self.instances)} instances")

if __name__ == "__main__":
    app = VerilogIntegrationTool()
    app.log("Verilog Integration Tool initialized. Use 'Open Module' to add Verilog modules.")
    app.log("Drag modules from the Module Library to the Instantiated Modules list.")
    app.mainloop()
