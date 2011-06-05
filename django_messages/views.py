# -*- coding:utf-8 -*-
import datetime

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_noop
from django.core.urlresolvers import reverse
from django.conf import settings

from django.db import transaction

from django.views.generic.list_detail import object_list, object_detail

from django_messages.models import Message
from django_messages.forms import ComposeForm, ReplyForm
from django_messages.utils import format_quote


@login_required
def message_list(request, queryset, paginate_by=25,
    extra_context=None, template_name=None):
    return object_list(request, queryset=queryset, paginate_by=paginate_by,
            extra_context=extra_context, template_name=template_name,
            template_object_name='message')
        

@login_required
def inbox(request, template_name='django_messages/inbox.html', **kw):
    """
    Displays a list of received messages for the current user.
    """
    kw['template_name'] = template_name
    queryset = Message.inbox.for_user(request.user)
    return message_list(request, queryset, **kw)


@login_required
def outbox(request, template_name='django_messages/outbox.html', **kw):
    """
    Displays a list of sent messages for the current user.
    """
    kw['template_name'] = template_name
    queryset = Message.outbox.for_user(request.user)
    return message_list(request, queryset, **kw)


@login_required
def trash(request, template_name='django_messages/trash.html', **kw):
    """
    Displays a list of deleted messages.
    """
    kw['template_name'] = template_name
    queryset = Message.trash.for_user(request.user)
    return message_list(request, queryset, **kw)


@login_required
@transaction.commit_on_success
def compose(request, recipient=None, form_class=ComposeForm,
        template_name='django_messages/compose.html', success_url=None,
        recipient_filter=None, extra_context=None):
    """
    Displays and handles the ``form_class`` form to compose new messages.
    Required Arguments: None
    Optional Arguments:
        ``recipient``: username of a `django.contrib.auth` User, who should
                       receive the message, optionally multiple usernames
                       could be separated by a '+'
        ``form_class``: the form-class to use
        ``template_name``: the template to use
        ``success_url``: where to redirect after successfull submission
        ``extra_context``: extra context dict
    """
    if request.method == "POST":
        form = form_class(request.user, data=request.POST,
                recipient_filter=recipient_filter)
        if form.is_valid():
            instance, message_list = form.save()
            Message.objects.send(message_list)
            messages.add_message(request, messages.SUCCESS, _(u"Message successfully sent."))
            return redirect(success_url or request.GET.get('next') or inbox)
    else:
        form = form_class(request.user, initial={'recipient': recipient})

    ctx = extra_context or {}
    ctx.update({
        'form': form,
        })

    return render_to_response(template_name, RequestContext(request, ctx))


@login_required
@transaction.commit_on_success
def reply(request, message_id, form_class=ReplyForm,
        template_name='django_messages/reply.html', success_url=None,
        recipient_filter=None, extra_context=None):
    """
    Prepares the ``form_class`` form for writing a reply to a given message
    (specified via ``message_id``). 
    """
    parent = get_object_or_404(Message, pk=message_id, owner=request.user)

    if request.method == "POST":
        form = form_class(request.user, parent, data=request.POST, 
                recipient_filter=recipient_filter)
        if form.is_valid():
            instance, message_list = form.save()
            Message.objects.send(message_list)
            messages.add_message(request, messages.SUCCESS, _(u"Message successfully sent."))
            return redirect(success_url or inbox)
    else:
        form = form_class(request.user, parent)

    ctx = extra_context or {}
    ctx.update({
        'form': form,
        })

    return render_to_response(template_name, 
            RequestContext(request, ctx))


@login_required
@transaction.commit_on_success
def delete(request, message_id, success_url=None):
    """
    Marks a message as deleted by sender or recipient. The message is not
    really removed from the database, because two users must delete a message
    before it's save to remove it completely.
    A cron-job should prune the database and remove old messages which are
    deleted by both users.
    As a side effect, this makes it easy to implement a trash with undelete.

    You can pass ?next=/foo/bar/ via the url to redirect the user to a different
    page (e.g. `/foo/bar/`) than ``success_url`` after deletion of the message.
    """
    
    message = get_object_or_404(Message, pk=message_id, owner=request.user)
    message.move_to_trash()
    message.save()
    messages.add_message(request, messages.SUCCESS, _(u"Message successfully deleted."))
    return redirect(request.GET.get('next') or success_url or inbox)


@login_required
@transaction.commit_on_success
def undelete(request, message_id, success_url=None):
    """
    Recovers a message from trash.
    """
    message = get_object_or_404(Message, pk=message_id, owner=request.user)
    message.undelete()
    message.save()

    message_view = inbox # should be dependent on message box (inbox,outbox)

    messages.add_message(request, messages.SUCCESS,
            _(u"Message successfully recovered."))
    return redirect(request.GET.get('next') or success_url or message_view)


@login_required
def view(request, message_id, template_name='django_messages/view.html',
        extra_context=None):
    """
    Shows a single message.``message_id`` argument is required.
    The user is only allowed to see the message, if he is either
    the sender or the recipient. If the user is not allowed a 404
    is raised.
    If the user is the recipient and the message is unread
    ``read_at`` is set to the current datetime.
    """
    message = get_object_or_404(Message, pk=message_id, owner=request.user)
    if message.is_unread():
        message.mark_read()
        message.save()
    ctx = extra_context or {}
    ctx.update({
        'message': message,
        })
    return render_to_response(template_name, RequestContext(request, ctx))

