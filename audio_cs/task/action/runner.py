import logging
from audio_cs.task.action.register import ActionRegister
from audio_cs.task.action.base import ActionResult, ActionCall
from audio_cs.domain.state import DialogueState

logger = logging.getLogger(__name__)


class ActionRunner:
    def __init__(self, registry: ActionRegister) -> None:
        self.registry = registry

    async def run(self, action_call: ActionCall, state: DialogueState) -> ActionResult:
        action_name = action_call.action_name
        logger.debug("执行 Action: %s", action_name)
        action = self.registry.get(action_name)
        return await action.run(state, action_call.action_kwargs)

