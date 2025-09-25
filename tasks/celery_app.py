from celery import Celery
from celery.signals import worker_process_init
from dotenv import load_dotenv

from config import settings
from utils.db_session import initialize_database

# Load environment variables from .env file for Celery workers
# This is crucial for ensuring workers have access to the same settings as the main app.
load_dotenv()

@worker_process_init.connect
def init_worker(**kwargs):
    """
    Signal handler to initialize resources for each Celery worker process.
    This is the key to preventing "event loop" errors with async database
    connections by ensuring each worker process creates its own engine.
    """
    print("Celery worker process initializing...")
    initialize_database()
    print("Celery worker process initialization complete.")

# Create the Celery application instance
celery_app = Celery(
    'DLBot_tasks',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        'tasks.download_tasks',
        'tasks.video_tasks'
    ]  # A list of modules to import when the worker starts.
)

# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

if __name__ == '__main__':
    celery_app.start()