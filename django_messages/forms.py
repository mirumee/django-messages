import datetime
from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext_noop
from django.contrib.auth.models import User

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
            self.fields['recipient']._recipient_filter = recipient_filter

    def create_recipient_message(self, recipient, message):
        return Message(
            owner = recipient,
            sender = self.sender,
            to = recipient.username,
            recipient = recipient,
            subject = message.subject,
            body = message.body,
        )

    def save(self, commit=True):
        recipients = self.cleaned_data['recipient']
        instance = super(ComposeForm, self).save(commit=False)

        message_list = []

        # clone messages in recipients inboxes
        for r in recipients:
            msg = self.create_recipient_message(r, instance)
            message_list.append(msg)

        instance.to = ','.join([r.username for r in recipients])

        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
         
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
        super(ReplyForm, self).__init__(self, sender, *args, **kw)
    
    def quote_message(self):
        return format_quote(self.sender, self.parent_message.body)

    def create_recipient_message(self, recipient, message):
        msg = super(ReplyForm, self).create_recipient_message(recipient, message)
        msg.replied_at = datetime.datetime.now()
        # msg.parent_msg = ???  find parent in recipient inbox, trash or set to null
        return msg

    def save(self, commit=True):
        instance, message_list = super(ReplyForm, self).save(commit=False)
        instance.replied_at = datetime.datetime.now()
        instance.parent_msg = self.parent_message
        if commit:
            instance.save()
            for msg in message_list:
                msg.save()
        return instance, message_list


"""
if notification:
    if parent_msg is not None:
        notification.send([r], "messages_reply_received", {'message': msg,})
    else:
        notification.send([r], "messages_received", {'message': msg,})
"""
