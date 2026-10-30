"""Importing this module registers every job handler with the queue registry."""

from reel2play import pipeline
from reel2play.intake import prepare
from reel2play.whatsapp import conversation, notify

HANDLER_MODULES = (prepare, pipeline, conversation, notify)
