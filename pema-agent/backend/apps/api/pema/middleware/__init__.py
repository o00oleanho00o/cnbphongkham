"""Inbound middleware: allowlist, rate limiter, message batcher (Redis, PendingInbox), thread run chain
(Redis ThreadLock). Owner: C1. Ported from src/middleware.
"""
