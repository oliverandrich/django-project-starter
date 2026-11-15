from django.db import models


class StreamEvent(models.Model):
    """A server-sent event, kept for replay after a reconnect. See events.py."""

    id = models.BigAutoField(primary_key=True)
    topic = models.CharField(max_length=200)
    event = models.CharField(max_length=100, blank=True)
    html = models.TextField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # A fixed name: the generated one derives from the project name, which startproject sets.
        indexes = [models.Index(fields=["topic", "id"], name="streamevent_topic_id")]

    def __str__(self) -> str:
        return f"{self.topic} #{self.id}"
