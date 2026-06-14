from __future__ import annotations

import asyncio

from courtvision.broadcast import event_bus
from courtvision.database import SessionFactory
from courtvision.inference import LoadedModel, active_model_resolver
from courtvision.ml import prediction_service
from courtvision.models import Game, PlayByPlayEvent
from courtvision.prediction_runtime import resolve_pregame_estimate
from courtvision.presenters import event_envelopes, status_envelope
from courtvision.repository import game_events, get_game, latest_prediction


class ReplayCoordinator:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._start_lock = asyncio.Lock()

    def is_running(self, game_id: str) -> bool:
        task = self._tasks.get(game_id)
        return task is not None and not task.done()

    async def start(self, game_id: str, tick_seconds: float) -> tuple[bool, int]:
        async with self._start_lock:
            if self.is_running(game_id):
                return False, 0

            async with SessionFactory() as session:
                game = await get_game(session, game_id)
                if game is None:
                    return False, 0
                prediction = await latest_prediction(session, game_id, "pregame")
                baseline = 0.5
                if prediction is not None:
                    pregame_runtime = await active_model_resolver.resolve(
                        session,
                        "pregame",
                    )
                    estimate = await resolve_pregame_estimate(
                        session,
                        prediction,
                        pregame_runtime,
                    )
                    baseline = estimate.probability
                live_runtime = await active_model_resolver.resolve(session, "live_win")
                events = await game_events(session, game_id)
            task = asyncio.create_task(
                self.run_once(
                    game,
                    baseline,
                    events,
                    tick_seconds,
                    live_runtime,
                )
            )
            self._tasks[game_id] = task
            task.add_done_callback(lambda completed: self._cleanup(game_id, completed))
            return True, len(events)

    async def run_game(self, game_id: str, tick_seconds: float) -> int:
        async with SessionFactory() as session:
            game = await get_game(session, game_id)
            if game is None:
                return 0
            prediction = await latest_prediction(session, game_id, "pregame")
            baseline = 0.5
            if prediction is not None:
                pregame_runtime = await active_model_resolver.resolve(
                    session,
                    "pregame",
                )
                estimate = await resolve_pregame_estimate(
                    session,
                    prediction,
                    pregame_runtime,
                )
                baseline = estimate.probability
            live_runtime = await active_model_resolver.resolve(session, "live_win")
            events = await game_events(session, game_id)
        await self.run_once(
            game,
            baseline,
            events,
            tick_seconds,
            live_runtime,
        )
        return len(events)

    async def run_once(
        self,
        game: Game,
        baseline: float,
        events: list[PlayByPlayEvent],
        tick_seconds: float,
        live_runtime: LoadedModel | None = None,
    ) -> None:
        envelopes = await event_envelopes(
            events,
            game,
            baseline,
            runtime=live_runtime,
        )
        live_model_version = (
            envelopes[0].model_version
            if envelopes
            else (
                live_runtime.version
                if live_runtime
                else prediction_service.live_model_version
            )
        )
        await event_bus.publish(
            status_envelope(
                game,
                sequence=0,
                event_type="source_status",
                payload={"status": "replay_started", "event_count": len(events)},
                model_version=live_model_version,
            )
        )
        for envelope in envelopes:
            await asyncio.sleep(tick_seconds)
            await event_bus.publish(envelope)

        last_sequence = events[-1].sequence if events else 0
        await event_bus.publish(
            status_envelope(
                game,
                sequence=last_sequence,
                event_type="replay_completed",
                payload={"status": "completed"},
                model_version=live_model_version,
            )
        )

    def _cleanup(self, game_id: str, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(game_id) is completed:
            self._tasks.pop(game_id, None)


replay_coordinator = ReplayCoordinator()
