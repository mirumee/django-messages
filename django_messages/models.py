import datetime
from django.db import models
from django.conf import settings
from django.db.models import signals
from django.db.models.query import QuerySet
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _


class MessageQueryset(QuerySet):
    def unread(self):
        return self.filter(unread=True)


class BaseMessageManager(models.Manager):
    def get_query_set(self):
        return MessageQueryset(self.model)
    
    def trash(self, messages):
        """
        move messages to trash
        """
        messages.update(deleted=True, deleted_at=datetime.datetime.now())

    def send(self, messages):
        """
        send messages
        """
        pass


class Inbox(BaseMessageManager):
    def get_query_set(self):
        return super(Inbox, self).get_query_set().filter(deleted=False)

    def for_user(self, user):
        """
        Returns all messages that were received by the given user and are not
        marked as deleted.
        """
        return self.get_query_set().filter(owner=user, recipient=user)


class Outbox(BaseMessageManager):
    def get_query_set(self):
        return super(Outbox, self).get_query_set().filter(deleted=False)

    def for_user(self, user):
        """
        Returns all messages that were sent by the given user and are not
        marked as deleted.
        """
        return self.get_query_set().filter(owner=user, sender=user)


class Trash(BaseMessageManager):
    """
    Trash manager
    """

    def get_query_set(self):
        return super(Trash, self).get_query_set().filter(deleted=True)

    def for_user(self, user):
        """
        Returns all messages that were either received or sent by the given
        user and are marked as deleted.
        """
        return self.get_query_set().filter(owner=user)


class Message(models.Model):
    """
    A private message from user to user
    """
    owner = models.ForeignKey(User, related_name='messages')
    to = models.CharField(max_length=255) # recipient usernames comma separated
    subject = models.CharField(_("Subject"), max_length=120)
    body = models.TextField(_("Body"))
    sender = models.ForeignKey(User, related_name='+', verbose_name=_("Sender"))
    recipient = models.ForeignKey(User, related_name='+', null=True, blank=True, verbose_name=_("Recipient"))
    thread = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    parent_msg = models.ForeignKey('self', related_name='next_messages', null=True, blank=True, verbose_name=_("Parent message"))
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    unread = models.BooleanField(default=True, db_index=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    replied_at = models.DateTimeField(_("replied at"), null=True, blank=True)
    deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(_("Sender deleted at"), null=True, blank=True)

    objects = BaseMessageManager()
    inbox = Inbox()
    outbox = Outbox()
    trash = Trash()
    
    def is_unread(self):
        """returns whether the recipient has read the message or not"""
        return bool(self.read_at is None)

    def undelete(self):
        self.deleted = False
        self.deleted_at = None

    def mark_read(self):
        self.unread = False
        self.read_at = datetime.datetime.now()

    def mark_unread(self):
        self.unread = True
        self.read_at = None

    def move_to_trash(self):
        self.deleted = True
        self.deleted_at = datetime.datetime.now()
        
    def replied(self):
        """returns whether the recipient has written a reply to this message"""
        return bool(self.replied_at is not None)
    
    def __unicode__(self):
        return self.subject

    def all_recipients(self):
        return User.objects.filter(username__in=self.to.split(','))
    
    @models.permalink
    def get_absolute_url(self):
        return ('messages_detail', (self.id,))
    
    class Meta:
        ordering = ['-sent_at']
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        db_table = 'messages_message'
        

def inbox_count_for(user):
    """
    returns the number of unread messages for the given user but does not
    mark them seen
    """
    return Message.inbox.for_user(user).unread().count()


# fallback for email notification if django-notification could not be found
if "notification" not in settings.INSTALLED_APPS:
    from django_messages.utils import new_message_email
    signals.post_save.connect(new_message_email, sender=Message)
