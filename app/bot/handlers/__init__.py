from aiogram import Router

from app.bot.handlers import add, cancel, categories, family, help, report, scan, settings, start


def setup_routers() -> Router:
    router = Router()
    router.include_router(start.router)
    router.include_router(help.router)
    router.include_router(cancel.router)
    router.include_router(add.router)
    router.include_router(scan.router)
    router.include_router(report.router)
    router.include_router(categories.router)
    router.include_router(family.router)
    router.include_router(settings.router)
    return router
