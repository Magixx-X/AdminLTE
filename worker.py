from app import create_app
from app.tasks.worker import Worker

if __name__ == '__main__':
    Worker(create_app({'PROCESS_ROLE': 'worker'})).run()
