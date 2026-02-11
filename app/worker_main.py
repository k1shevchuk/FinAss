from arq import run_worker

from app.infra.queue.arq_worker import WorkerSettings


def main() -> None:
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
