"""启动脚本"""

import uvicorn
from app.api.main import app
from app.core.config import get_settings


if __name__ == "__main__":
    settings = get_settings()

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        # 交付启动脚本固定使用单进程模式，避免 Windows reload 子进程加载到旧模块。
        # 本地热更新请显式执行：uvicorn app.api.main:app --reload
        reload=False,
        log_level=settings.log_level.lower(),
        timeout_keep_alive=300
    )
