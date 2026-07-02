---
title: Conversational Assessment Recommender
emoji: 🧭
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Conversational SHL Assessment Recommender

A stateless conversational agent that recommends SHL individual test solutions
through multi-turn dialogue. See [APPROACH.md](APPROACH.md) for design details.

- `GET /health` — readiness check
- `POST /chat` — stateless chat endpoint, takes full conversation history
