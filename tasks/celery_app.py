from celery import Celery
from config import settings

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
