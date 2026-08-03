from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from beanie.operators import Set

from bot.constants import MAIN_MENU_LABELS, MENU_HELP
from bot.deeplinks import resolve_pending_action
from bot.enums import Messages
from bot.keyboards import main_menu_kb
from bot.models import User
from bot.timeutils import parse_utc_offset

router = Router()


class SetTimezone(StatesGroup):
    waiting_offset = State()


async def ensure_timezone(message: Message, state: FSMContext) -> bool:
    """Ask for the user's UTC offset if it's not set yet.

    Returns True if the caller may proceed, False if it just asked for the
    offset and the caller should stop (the user will need to repeat their
    original command afterwards).
    """
    user = await User.find_one(User.user_id == message.from_user.id)
    if user is not None and user.utc_offset_minutes is not None:
        return True

    await state.set_state(SetTimezone.waiting_offset)
    await message.answer(Messages.ASK_TIMEZONE)
    return False


async def _show_pending_action(message: Message, payload: str) -> None:
    """Render the share/assign/pool-invite a /start deep-link carried."""
    resolved = await resolve_pending_action(payload)
    if resolved is None:
        return
    text, markup = resolved
    await message.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    command: CommandObject = CommandObject(command="start"),
):
    payload = (command.args or "").strip() or None
    if not await ensure_timezone(message, state):
        if payload:
            await state.update_data(pending_payload=payload)
        return
    await message.answer(Messages.WELCOME, reply_markup=main_menu_kb())
    if payload:
        await _show_pending_action(message, payload)


@router.message(
    SetTimezone.waiting_offset, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def set_timezone(message: Message, state: FSMContext):
    offset_minutes = parse_utc_offset(message.text)
    if offset_minutes is None:
        await message.answer(Messages.INVALID_OFFSET)
        return

    data = await state.get_data()
    await User.find_one(User.user_id == message.from_user.id).upsert(
        Set({User.utc_offset_minutes: offset_minutes}),
        on_insert=User(
            user_id=message.from_user.id,
            username=message.from_user.username,
            utc_offset_minutes=offset_minutes,
        ),
    )
    await state.clear()
    await message.answer(Messages.TIMEZONE_SAVED)
    await message.answer(Messages.WELCOME, reply_markup=main_menu_kb())
    payload = data.get("pending_payload")
    if payload:
        await _show_pending_action(message, payload)


@router.message(Command("help"))
@router.message(F.text == MENU_HELP)
async def cmd_help(message: Message):
    await message.answer(Messages.HELP, reply_markup=main_menu_kb())
