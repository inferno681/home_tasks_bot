import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from beanie.operators import Set

from bot.keyboards import main_menu_kb
from bot.models import User

router = Router()

# ponytail: фиксированное смещение вместо zoneinfo — не учитывает переход на
# летнее/зимнее время; апгрейд на IANA-таймзону, если это станет проблемой.
OFFSET_RE = re.compile(r"^([+-])(\d{1,2})(?::(\d{2}))?$")

WELCOME = (
    "Привет! Я помогу отслеживать домашние дела.\n\n"
    "/new — добавить задачу (текст, фото или оба)\n"
    "/list — список открытых задач\n"
    "/share <id задачи> <@username> — расшарить задачу\n"
    "/assign <id задачи> <@username> — назначить ответственного\n"
    "/help — помощь"
)


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
    await message.answer(
        "Сначала укажи свой часовой пояс как смещение от UTC (например +3 "
        "или -5) — так напоминания будут приходить вовремя. После этого "
        "повтори команду."
    )
    return False


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not await ensure_timezone(message, state):
        return
    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.message(SetTimezone.waiting_offset, F.text)
async def set_timezone(message: Message, state: FSMContext):
    m = OFFSET_RE.match(message.text.strip())
    if not m:
        await message.answer("Не понял. Пример: +3 или +5:30 или -5.")
        return

    sign, hh, mm = m.groups()
    sign_multiplier = 1 if sign == "+" else -1
    total_minutes = int(hh) * 60 + int(mm or 0)
    offset_minutes = sign_multiplier * total_minutes
    if not -12 * 60 <= offset_minutes <= 14 * 60:
        await message.answer("Смещение должно быть в пределах -12:00..+14:00.")
        return

    await User.find_one(User.user_id == message.from_user.id).upsert(
        Set({User.utc_offset_minutes: offset_minutes}),
        on_insert=User(
            user_id=message.from_user.id,
            username=message.from_user.username,
            utc_offset_minutes=offset_minutes,
        ),
    )
    await state.clear()
    await message.answer("Часовой пояс сохранён.")
    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "/new — создать задачу. Пришли текст и/или фото, затем срок "
        "(или 'нет').\n"
        "/list [категория] — открытые задачи с кнопками отметки выполнения.\n"
        "/share <id задачи> <@username> — расшарить задачу (id из /list).\n"
        "/assign <id задачи> <@username> — назначить ответственного.\n"
        "/cancel — отменить текущий диалог.",
        reply_markup=main_menu_kb(),
    )
