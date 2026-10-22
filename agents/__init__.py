# -*- coding: utf-8 -*-
"""
agents/__init__.py — Agent registry for the whole system.
"""

from agents.base import BaseAgent, set_global_pause
from agents.agent1_leads import WebsiteLeadManager
from agents.agent2_whatsapp import WhatsAppAgent
from agents.agent3_instagram import InstagramAgent
from agents.agent4_facebook import FacebookAgent
from agents.agent5_tiktok import TikTokAgent

AGENTS = {
    "1": WebsiteLeadManager(),
    "2": WhatsAppAgent(),
    "3": InstagramAgent(),
    "4": FacebookAgent(),
    "5": TikTokAgent(),
}


def get(agent_id) -> BaseAgent:
    key = str(agent_id)
    if key not in AGENTS:
        raise KeyError(f"No agent {agent_id}")
    return AGENTS[key]


def all_agents():
    return list(AGENTS.values())


def start_all():
    for a in AGENTS.values():
        a.start()


def stop_all():
    for a in AGENTS.values():
        a.stop()


def set_auto_send_all(value: bool):
    for a in AGENTS.values():
        a.auto_send = value


__all__ = ["AGENTS", "get", "all_agents", "start_all", "stop_all",
           "set_auto_send_all", "set_global_pause", "BaseAgent"]