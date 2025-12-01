#!/bin/bash
# 测试环境启动脚本
# 用法:
#   ./scripts/start_test.sh        # 如运行中 -> 先停再启；如未运行 -> 启动
#   ./scripts/start_test.sh stop   # 停止服务
#   ./scripts/start_test.sh status # 查看状态

APP_NAME="tender_ontology"
PORT=39103

# 日志目录和文件（按日期）
LOG_DIR="log"
mkdir -p "$LOG_DIR"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/uvicorn_${PORT}_${TODAY}.log"
PID_FILE=".pid_${PORT}"

# 环境变量
export LD_LIBRARY_PATH=
export HF_HOME=/data/LLM_group/HuggingFace
export HF_HUB_CACHE=/data/LLM_group/HuggingFace/Hub
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=2
export STORAGE_MODE=local
export ENV=test

# 查找进程
find_pid() {
    ps aux | grep "uvicorn tender_ontology.main:app" | grep -v grep | awk '{print $2}'
}

# 停止服务
stop_service() {
    # 先杀占用端口的进程
    PORT_PID=$(lsof -ti:$PORT 2>/dev/null)
    if [ -n "$PORT_PID" ]; then
        echo "[${APP_NAME}] 发现端口 $PORT 被占用，PID: $PORT_PID"
        kill $PORT_PID 2>/dev/null
        sleep 1
        # 如果还在，强制杀
        if lsof -ti:$PORT > /dev/null 2>&1; then
            kill -9 $(lsof -ti:$PORT) 2>/dev/null
        fi
    fi

    # 再杀 uvicorn 进程
    PID=$(find_pid)
    if [ -n "$PID" ]; then
        echo "[${APP_NAME}] 正在停止进程 PID: $PID ..."
        kill $PID 2>/dev/null
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID 2>/dev/null
        fi
        echo "[${APP_NAME}] 已停止"
    else
        echo "[${APP_NAME}] uvicorn 进程未运行"
    fi

    # 确保端口已释放
    sleep 1
    if lsof -ti:$PORT > /dev/null 2>&1; then
        echo "[${APP_NAME}] 警告: 端口 $PORT 仍被占用，强制释放..."
        kill -9 $(lsof -ti:$PORT) 2>/dev/null
        sleep 1
    fi
}

# 启动服务（不做是否已运行判断，外层保证）
start_service() {
    echo "[${APP_NAME}] 启动服务..."
    echo "[${APP_NAME}] 环境: $ENV"
    echo "[${APP_NAME}] 端口: $PORT"

    nohup python -m uvicorn tender_ontology.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --reload \
        > "$LOG_FILE" 2>&1 &

    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"

    sleep 2
    if ps -p "$NEW_PID" > /dev/null 2>&1; then
        echo "[${APP_NAME}] 启动成功 PID: $NEW_PID"
        echo "[${APP_NAME}] 日志文件: $LOG_FILE"
        echo "[${APP_NAME}] 查看日志: tail -f $LOG_FILE"
    else
        echo "[${APP_NAME}] 启动失败，请检查日志: $LOG_FILE"
        return 1
    fi
}

# 查看状态
status_service() {
    PID=$(find_pid)
    if [ -n "$PID" ]; then
        echo "[${APP_NAME}] 运行中 PID: $PID"
        echo "[${APP_NAME}] 端口: $PORT"
        echo "[${APP_NAME}] 环境: $ENV"
    else
        echo "[${APP_NAME}] 未运行"
    fi
}

# 主逻辑：默认行为 = 如果在跑就重启，不在跑就启动
case "${1:-start}" in
    start)
        PID=$(find_pid)
        if [ -n "$PID" ]; then
            echo "[${APP_NAME}] 检测到服务已在运行 PID: $PID，先停止再重启..."
            stop_service
            sleep 1
        else
            echo "[${APP_NAME}] 服务未运行，直接启动..."
        fi
        start_service
        ;;
    stop)
        stop_service
        ;;
    status)
        status_service
        ;;
    *)
        echo "用法: $0 {start|stop|status}"
        exit 1
        ;;
esac