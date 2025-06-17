# ai_vbuilder
 AI generated Verilog Builder
 AI generated README

 # Verilog Integration Tool

## 概述

Verilog Integration Tool 是一个基于 Python 和 Tkinter 的图形化工具，用于集成和管理 Verilog/SystemVerilog 模块。它提供了一个直观的界面，让您能够：

1. 解析 Verilog 模块的端口和参数
2. 实例化模块并管理实例
3. 配置端口连接和参数值
4. 自动生成顶层模块代码
5. 保存和加载项目状态

## 主要功能

### 1. 模块管理
- 打开并解析 Verilog/SystemVerilog 文件
- 显示模块的端口、参数和宏定义
- 支持多维端口和参数类型
- 右键菜单支持刷新和删除模块

### 2. 实例管理
- 通过拖放方式实例化模块
- 自定义实例名称
- 右键菜单支持重命名和删除实例
- 删除实例时自动清理相关连接

### 3. 端口和参数配置
- 为每个端口选择连接类型：input/output/wire
- 设置信号名称（端口名称或线网名称）
- 配置参数值
- 内联编辑功能，支持下拉菜单和手动输入

### 4. 代码生成
- 自动生成符合 Verilog/SystemVerilog 标准的顶层模块
- 智能处理位宽声明（[Width-1:0] 格式）
- 位宽为1时省略位宽声明
- 自动生成输入/输出端口和内部线网
- 在实例上方添加源文件路径注释

### 5. 项目管理
- 保存项目为 Verilog 文件
- 文件末尾包含 BASE64 编码的项目数据
- 打开保存的文件恢复完整项目状态
- 详细的日志输出

## 安装与运行

### 系统要求
- Python 3.6 或更高版本
- Tkinter（通常随 Python 一起安装）

### 安装依赖
```bash
pip install pybase64
```

### 运行程序
```bash
python verilog_integration_tool.py
```

## 使用说明

### 1. 打开模块
1. 点击 "Open Module" 按钮
2. 选择 Verilog/SystemVerilog 文件（.v 或 .sv）
3. 解析后的模块会显示在左侧蓝色列表（Module Library）中

### 2. 实例化模块
1. 从蓝色列表（Module Library）拖动模块到黄色列表（Instantiated Modules）
2. 输入实例名称（默认为 u_模块名）
3. 实例会显示在黄色列表中

### 3. 配置端口和参数
1. 在黄色列表中选择一个实例
2. 在右侧绿色列表（Ports and Parameters）中配置：
   - **Connection 列**：选择端口连接类型（input/output/wire）
   - **Name 列**：输入信号名称（端口名称或线网名称）
   - **参数**：在第二列输入参数值

### 4. 管理实例
- **重命名实例**：右键点击实例 → "Rename"
- **删除实例**：右键点击实例 → "Delete"

### 5. 管理模块
- **刷新模块**：右键点击模块 → "Refresh"（重新解析文件）
- **删除模块**：右键点击模块 → "Delete"（需无实例使用）

### 6. 保存和加载项目
- **保存项目**：点击 "Save Project"，生成顶层 Verilog 文件
- **加载项目**：点击 "Open Project"，打开之前保存的文件

## 文件格式说明

生成的顶层 Verilog 文件包含：
1. 模块声明
2. 端口声明（input/output）
3. 线网声明（wire）
4. 实例化子模块
5. 每个实例上方的源文件路径注释
6. 文件末尾的 BASE64 编码项目数据（以 `// VERILOG_TOOL_DATA:` 开头）

示例：
```verilog
// Auto-generated top module: top_module
module top_module (
  input wire [7:0] data_in,
  output wire [7:0] data_out
);

  wire [7:0] internal_wire;

  // Source: /path/to/module1.v
  module1 #(
    .PARAM1(8),
    .PARAM2("value")
  ) u_module1 (
    .port1(data_in),
    .port2(internal_wire)
  );
  
  // Source: /path/to/module2.v
  module2 u_module2 (
    .portA(internal_wire),
    .portB(data_out)
  );

endmodule

// VERILOG_TOOL_DATA: eyJtb2R1bGVzIjp7...
```

## 注意事项

1. **位宽处理**：
   - 位宽为1时不生成位宽声明
   - 数字位宽自动转换为 [N-1:0] 格式
   - 表达式位宽保持原样

2. **连接规则**：
   - 输入端口必须连接到 `input` 类型
   - 输出端口必须连接到 `output` 类型
   - 内部连接使用 `wire` 类型

3. **兼容性**：
   - 支持 Verilog 和 SystemVerilog 语法
   - 支持多维端口和参数类型
   - 支持宏定义处理

4. **限制**：
   - 删除模块前需确保无实例使用
   - 实例名称必须唯一
   - 目前不支持分层模块解析

## 开发与贡献

欢迎贡献代码和改进建议！请遵循以下步骤：
1. Fork 项目仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -am 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
