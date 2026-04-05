#!/bin/bash
# 启动脚本

# 检查 Python 版本
python3 --version

# 安装依赖
pip install -r requirements.txt

# 运行服务
python3 main.py
