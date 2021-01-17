import sys

from telegram.ext import Updater
from telegram.ext import CommandHandler
import logging
import dns.query
import dns.exception
import os

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# DNS query parameters
TEST_DOMAIN = os.environ.get('TEST_DOMAIN', 'google.com')
DNS_IP = os.environ.get('DNS_IP')
DNS_HOST = os.environ.get('DNS_HOST')
TIMEOUT = int(os.environ.get('TIMEOUT', 5))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', 20))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    print('TELEGRAM_BOT_TOKEN needs to be set', file=sys.stderr)

if not DNS_IP:
    print('DNS_IP needs to be set', file=sys.stderr)

if not DNS_HOST:
    print('DNS_HOST needs to be set', file=sys.stderr)

# Global variable used for avoiding multiple "down" messages.
consecutiveFailures = 0


def start(update, context):
    """Append job to queue and send welcome message."""
    global consecutiveFailures
    consecutiveFailures = 0
    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context)
    context.job_queue.run_repeating(silent_check, CHECK_INTERVAL, 0, context=chat_id, name=str(chat_id))
    context.bot.send_message(chat_id=update.effective_chat.id, text="Hey. I am having a look on the dot.\n"
                                                                    "If you want me to make an "
                                                                    "unscheduled extra check type /poke. Stop me with "
                                                                    "/stop")


def remove_job_if_exists(name, context):
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def stop(update, context):
    """Remove job from queue and send confirm message."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = 'Subscription successfully cancelled!' if job_removed else 'You have no active subscription. Use /start to ' \
                                                                      'start it again.'
    update.message.reply_text(text)


def poke(update, context):
    """Allows to make a unscheduled test if dot is up or down."""

    test_domain = TEST_DOMAIN
    rdatatype = dns.rdatatype.A

    if len(context.args) >= 1:
        test_domain = context.args[0]

    if len(context.args) == 2:
        rdatatype = dns.rdatatype.from_text(context.args[1])

    try:
        r = dns.query.tls(
            dns.message.make_query(test_domain, rdtype=rdatatype),
            DNS_IP,
            server_hostname=DNS_HOST,
            timeout=TIMEOUT,
        )

        message = str('\n'.join(map(str, r.answer))) + '\nEverything seems fine. The dot is resolving #LikeABosch.'
        context.bot.sendDocument(
            chat_id=update.effective_chat.id,
            document='https://media1.tenor.com/images/5a5b26e19c0df8b4d602103c454dba80/tenor.gif?itemid=5177277',
            caption='✅ ' + str(message),
        )
    except dns.exception.DNSException as error:
        context.bot.sendDocument(
            chat_id=update.effective_chat.id,
            document='https://media1.tenor.com/images/a34763736bfa3469bfba1abe4c082071/tenor.gif?itemid=9390989',
            caption='🚨 ' + str(error),
        )


def silent_check(context):
    """Performs a silent check. Message is only sent if there is a problem."""
    global consecutiveFailures
    try:
        dns.query.tls(
            dns.message.make_query(TEST_DOMAIN, dns.rdatatype.A),
            DNS_IP,
            server_hostname=DNS_HOST,
            timeout=TIMEOUT,
        )
        # for answer in r.answer:
        #     message = str(answer) + '\nEverything seems fine. The dot is resolving like a king.'
        #     context.bot.send_message(context.job.context, text=str(message))
        if consecutiveFailures > 0:
            context.bot.send_message(context.job.context, text=str('Dot is up again!'))
            context.bot.sendDocument(
                context.job.context,
                document='https://media.giphy.com/media/Sk3KytuxDQJQ4/giphy.gif',
                caption='✅ DoT is back up',
            )
            consecutiveFailures = 0
    except dns.exception.DNSException as error:
        consecutiveFailures += 1
        print('DNS error: ', error, 'message no.', consecutiveFailures)
        if consecutiveFailures == 2:
            context.bot.sendDocument(
                context.job.context,
                document='https://media1.tenor.com/images/a34763736bfa3469bfba1abe4c082071/tenor.gif?itemid=9390989',
                caption='🚨 DoT is unreachable!\n' + str(error),
            )


def error_callback(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Run bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("poke", poke))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_error_handler(error_callback)

    # Add @dotmonitor channel to job_queue
    updater.job_queue.run_repeating(silent_check, CHECK_INTERVAL, 0, context='@dotmonitor', name=str('@dotmonitor'))

    # Start the Bot
    updater.start_polling()

    # Block until you press Ctrl-C or the process receives SIGINT, SIGTERM or
    # SIGABRT. This should be used most of the time, since start_polling() is
    # non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
