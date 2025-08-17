#!/usr/bin/env python3
"""Add support channel to chat system."""

from chat_models import ensure_channel_by_name

if __name__ == "__main__":
    channel = ensure_channel_by_name("support")
    print(f"Support channel exists with ID: {channel.id}")