import datetime
from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext_noop
from django.contrib.auth.models import User
import uuid

if "notification" in settings.INSTALLED_APPS:
    from notification import models as notification
else:
    notification = None

from django_messages.models import Message
from django_messages.fields import CommaSeparatedUserField
from django_messages.utils import format_quote


class MessageForm(forms.ModelForm):
    """
    base message form
    """
    recipients = CommaSeparatedUserField(label=_(u"Recipient"))
    subject = forms.CharField(label=_(u"Subject"))
    body = forms.CharField(label=_(u"Body"),
        widget=forms.Textarea(attrs={'rows': '12', 'cols':'55'}))

    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body',)

    def __init__(self, sender, *args, **kw):
        recipient_filter = kw.pop('recipient_filter', None)
        self.sender = sender
        super(MessageForm, self).__init__(*args, **kw)
        if recipient_filter is not None:
            self.fields['recipients']._recipient_filter = recipient_filter

    def create_recipient_message(self, recipient, message):
        return Message(
            owner = recipient,
            sender = self.sender,
            to = recipient.username,
            recipient = recipient,
            subject = message.subject,
            body = message.body,
            thread = message.thread,
            sent_at = message.sent_at,
        )

    def get_thread(self, message):
        return message.thread or uuid.uuid4().hex

    def save(self, commit=True):
        recipients = self.cleaned_data['recipients']
        instance = super(MessageForm, self).save(commit=False)
        instance.sender = self.sender
        instance.owner = self.sender
        instance.recipient = recipients[0]
        instance.thread = self.get_thread(instance)
        instance.unread = False
        instance.sent_at = datetime.datetime.now()

        message_list = []

        # clone messages in recipients inboxes
        for r in recipients:
            if r == self.sender: # skip duplicates
                continue
            msg = self.create_recipient_message(r, instance)
            message_list.append(msg)

        instance.to = ','.join([r.username for r in recipients])

        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
                if notification:
                    notification.send([msg.recipient], 
                            "messages_received", {'message': msg,})
         
        return instance, message_list


class ComposeForm(MessageForm):
    """
    A simple default form for private messages.
    """

    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body',)
    

class ReplyForm(MessageForm):
    """
    reply to form
    """
    class Meta:
        model = Message
        fields = ('recipients', 'subject', 'body',)

    def __init__(self, sender, message, *args, **kw):
        self.parent_message = message
        initial = kw.pop('initial', {})
        initial['recipients'] = message.sender.username
        initial['body'] = self.quote_message(message)
        initial['subject'] = self.quote_subject(message.subject)
        kw['initial'] = initial
        super(ReplyForm, self).__init__(sender, *args, **kw)
    
    def quote_message(self, original_message):
        return format_quote(original_message.sender, original_message.body)

    def quote_subject(self, subject):
        return u'Re: %s' % subject

    def create_recipient_message(self, recipient, message):
        msg = super(ReplyForm, self).create_recipient_message(recipient, message)
        msg.replied_at = datetime.datetime.now()

        # find parent in recipient messages
        try:
            msg.parent_msg = Message.objects.get(
                owner=recipient,
                sender=message.recipient,
                recipient=message.sender,
                thread=message.thread)
        except (Message.DoesNotExist, Message.MultipleObjectsReturned):
            # message may be deleted 
            pass

        return msg


    def get_thread(self, message):
        return self.parent_message.thread

    def save(self, commit=True):
        instance, message_list = super(ReplyForm, self).save(commit=False)
        instance.replied_at = datetime.datetime.now()
        instance.parent_msg = self.parent_message
        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
                if notification:
                    notification.send([msg.recipient],
                            "messages_reply_received", {
                                'message': msg,
                                'parent_msg': self.parent_message,
                                })
        return instance, message_list


