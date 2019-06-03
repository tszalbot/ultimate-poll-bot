"""Handle messages."""
from pollbot.helper.session import session_wrapper
from pollbot.helper.enums import ExpectedInput, VoteType
from pollbot.helper.creation import next_option
from pollbot.helper.display import get_options_text
from pollbot.helper.update import update_poll_messages
from pollbot.telegram.keyboard.options import get_options_keyboard
from pollbot.telegram.callback_handler.creation import create_poll

from pollbot.models import PollOption, Reference


@session_wrapper()
def handle_private_text(bot, update, session, user):
    """Read all private messages and the creation of polls."""
    # The user is currently not editing or creating a poll. Just ignore it
    if user.current_poll is None or user.current_poll.expected_input is None:
        return

    text = update.message.text.strip()
    poll = user.current_poll
    chat = update.message.chat
    expected_input = ExpectedInput[user.current_poll.expected_input]

    # Add the name
    if expected_input == ExpectedInput.name:
        poll.name = text
        poll.expected_input = ExpectedInput.description.name
        chat.send_message('Now send me the description')

    # Add the description
    elif expected_input == ExpectedInput.description:
        poll.description = text
        poll.expected_input = ExpectedInput.options.name
        message = 'Now send me the first option (Or send multiple options at once, each option on a new line)'
        chat.send_message(message)

    # Add an option to the poll
    elif expected_input == ExpectedInput.options:
        # Multiple options can be sent at once separated by newline
        # Strip them and ignore empty lines
        added_options = add_options(poll, text)

        if len(added_options) == 0:
            return "❌ No new options have been added."

        next_option(chat, poll, added_options)

    # Get the amount of possible votes per user for this poll
    elif expected_input == ExpectedInput.vote_count:
        if poll.vote_type == VoteType.limited_vote.name:
            error_message = f"Please send me a number between 1 and {len(poll.options)}"
        elif poll.vote_type == VoteType.cumulative_vote.name:
            error_message = "Please send me a number bigger than 0"

        try:
            amount = int(text)
        except BaseException:
            return error_message

        # Check for valid count
        if amount < 1 or (poll.vote_type == VoteType.limited_vote.name and amount > len(poll.options)):
            return error_message

        poll.number_of_votes = amount

        create_poll(session, poll, user, chat)

    # Add new options after poll creation
    elif expected_input == ExpectedInput.new_option:
        added_options = add_options(poll, text)

        if len(added_options) > 0:
            text = 'Options have been added:\n'
            for option in added_options:
                text += f'\n*{option}*'
            chat.send_message(text, parse_mode='markdown')
        else:
            chat.send_message('No new option has been added')

        # Reset expected input
        poll.expected_input = None

        text = get_options_text(poll)
        keyboard = get_options_keyboard(poll)
        message = chat.send_message(
            text,
            parse_mode='markdown',
            reply_markup=keyboard,
        )

        # Delete old references
        session.query(Reference) \
            .filter(Reference.poll == poll) \
            .filter(Reference.admin_chat_id == chat.id) \
            .delete()

        # Create new reference
        reference = Reference(
            poll,
            admin_chat_id=chat.id,
            admin_message_id=message.message_id
        )
        session.add(reference)
        session.commit()

        update_poll_messages(session, bot, poll)


def add_options(poll, text):
    """Add a new option to the poll."""
    options_to_add = [x.strip() for x in text.split('\n') if x.strip() != '']
    added_options = []

    for option_to_add in options_to_add:
        if option_is_duplicate(poll, options_to_add):
            continue

        poll_option = PollOption(poll, option_to_add)
        poll.options.append(poll_option)

        added_options.append(option_to_add)

    return added_options


def option_is_duplicate(poll, option_to_add):
    """Check whether this option already exists on this poll."""
    for existing_option in poll.options:
        if existing_option.name == option_to_add:
            return True

    return False
