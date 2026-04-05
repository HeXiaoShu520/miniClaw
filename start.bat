@echo off
chcp 65001 >nul
REM 启动脚本

REM 检查 Python 版本
python --version

REM 安装依赖
pip install -r requirements.txt

REM 运行服务
python main.py
