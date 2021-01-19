import random
import sys
import requests
from requests import RequestException
from requests.auth import HTTPBasicAuth
from telegram.ext import Updater
from telegram.ext import CommandHandler
import logging
import dns.query
import dns.exception
import os
import locale
import json

# Set locale
locale.setlocale(locale.LC_ALL, "de_DE.UTF8")

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
PIHOLE_HTTP_BASIC_AUTH_USER = os.environ.get('PIHOLE_HTTP_BASIC_AUTH_USER')
PIHOLE_HTTP_BASIC_AUTH_PWD = os.environ.get('PIHOLE_HTTP_BASIC_AUTH_PWD')
PIHOLE_API_URL = os.environ.get('PIHOLE_API_URL')
MAIN_CHANNEL = os.environ.get('MAIN_CHANNEL')


RANDOM_POSITIVE_GIFS = [
    'https://media1.tenor.com/images/5a5b26e19c0df8b4d602103c454dba80/tenor.gif?itemid=5177277',
    'https://media.giphy.com/media/Sk3KytuxDQJQ4/giphy.gif',
    'https://media1.tenor.com/images/9b42522f041a7bb7e2c75a8f2e79ba90/tenor.gif?itemid=5762334',
    'https://media1.tenor.com/images/774acad780cbd690b5291e942866269c/tenor.gif?itemid=5122518',
    'https://media1.tenor.com/images/6ef46d3ace15910c3814796d489160fb/tenor.gif?itemid=14611487',
    'https://media1.tenor.com/images/7c02ebe55ca7a950f816d2609f37086f/tenor.gif?itemid=11928987',
    'https://media1.tenor.com/images/ab284fe03692507c6943d80ccc109dd9/tenor.gif?itemid=5102354',
    'https://media1.tenor.com/images/b23a908ae01021bc1064937bad061b11/tenor.gif?itemid=7953536',
    'https://media1.tenor.com/images/c815396f481f2e27a36f48149cfe27c4/tenor.gif?itemid=10889686',
    'https://media1.tenor.com/images/6bde0a3fb2796a908e85e8704c910f23/tenor.gif?itemid=12275806',
    'https://media1.tenor.com/images/99f79b368759c8117f3599b9ef0b8a10/tenor.gif?itemid=9581464',
    'https://media1.tenor.com/images/3afba750e7f7acbaecde5c43ac192127/tenor.gif?itemid=13756050',
    'https://media1.tenor.com/images/c17b2cdb406f209c9b78ae1b8d0097b2/tenor.gif?itemid=13335250',
]

RANDOM_NEGATIVE_GIFS = [
    'https://media1.tenor.com/images/a34763736bfa3469bfba1abe4c082071/tenor.gif?itemid=9390989',
    'https://media1.tenor.com/images/7497db91e124928aaddca8a209ac9f3e/tenor.gif?itemid=5168755',
    'https://media1.tenor.com/images/7fbd19af37f516713d86e33b16997dd9/tenor.gif?itemid=4895737',
    'https://media1.tenor.com/images/c289b6327705e42674e3981a0972bc52/tenor.gif?itemid=4732213',
    'https://media1.tenor.com/images/4f6d3bba0006171ef081a8a6d3a372a0/tenor.gif?itemid=9178158',
    'https://media1.tenor.com/images/02259d16d192ffb8950cef62e1ed048d/tenor.gif?itemid=5079872',
    'https://media1.tenor.com/images/7fd5c29195518f21fa2164971bb4af8d/tenor.gif?itemid=13335249',
]

if not TELEGRAM_BOT_TOKEN:
    print('TELEGRAM_BOT_TOKEN needs to be set', file=sys.stderr)

if not DNS_IP:
    print('DNS_IP needs to be set', file=sys.stderr)

if not DNS_HOST:
    print('DNS_HOST needs to be set', file=sys.stderr)

# Global variable used for avoiding multiple "down" messages.
consecutive_failures = 0
subscribed_chat_ids = {MAIN_CHANNEL}

if os.path.isfile('/data/subscriptions.json'):
    file = open('/data/subscriptions.json', 'r')
    subscribed_chat_ids = set(json.load(file))
    file.close()
    logger.info('Subscriptions loaded.')


def persist_subscriptions():
    if os.path.isdir('/data'):
        file = open('/data/subscriptions.json', 'w')
        json.dump(list(subscribed_chat_ids), file)
        file.close()


def start(update, context):
    """Append job to queue and send welcome message."""
    global consecutive_failures
    consecutive_failures = 0
    chat_id = update.message.chat_id

    channel_link = 'https://t.me/' + MAIN_CHANNEL[1:]
    subscribed_chat_ids.add(chat_id)
    context.bot.send_message(chat_id=update.effective_chat.id, text="Hey. I am having a look on the dot.\n"
                                                                    "If you want me to make an "
                                                                    "unscheduled extra check type /poke. Stop me with "
                                                                    "/stop. Feel free to join " + channel_link)
    persist_subscriptions()


def stop(update, context):
    """Remove job from queue and send confirm message."""
    chat_id = update.message.chat_id

    try:
        subscribed_chat_ids.remove(chat_id)
        persist_subscriptions()
        update.message.reply_text('Subscription successfully cancelled!')
    except ValueError:
        update.message.reply_text('You have no active subscription. Use /start to start it again.')


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

        if r.rcode() == dns.rcode.NXDOMAIN:
            raise Exception('Domain not found, DoT is working though.')

        message = str('\n'.join(map(str, r.answer))) + '\nEverything seems fine. The dot is resolving #LikeABosch.'
        context.bot.send_document(
            chat_id=update.effective_chat.id,
            reply_to_message_id=update.message.message_id,
            document=random.choice(RANDOM_POSITIVE_GIFS),
            caption='✅ ' + str(message),
        )
    except dns.exception.DNSException as error:
        context.bot.send_document(
            chat_id=update.effective_chat.id,
            reply_to_message_id=update.message.message_id,
            document=random.choice(RANDOM_NEGATIVE_GIFS),
            caption='🚨 ' + str(error),
        )
    except Exception as error:
        context.bot.send_document(
            chat_id=update.effective_chat.id,
            reply_to_message_id=update.message.message_id,
            document=random.choice(RANDOM_NEGATIVE_GIFS),
            caption='⚠️ ' + str(error),
        )


def get_stats():
    """"Retrieve stats from pihole api. Requires HTTPBasicAuth."""
    message = "Stats not available."
    try:
        response = requests.get(PIHOLE_API_URL,
                                auth=HTTPBasicAuth(PIHOLE_HTTP_BASIC_AUTH_USER,
                                                   PIHOLE_HTTP_BASIC_AUTH_PWD))
        data = response.json()
        total_queries = data.get('dns_queries_today')
        queries_blocked = data.get('ads_blocked_today')
        percent_blocked = data.get('ads_percentage_today')
        domains_on_blocklist = data.get('domains_being_blocked')
        message = "Total Queries: " + f'{total_queries:n}' \
                  + "\nQueries Blocked: " + f'{queries_blocked:n}' \
                  + "\nPercent Blocked: " + f'{percent_blocked:n}%' \
                  + "\nDomains on Blocklist: " + f'{domains_on_blocklist:n}' \
                  + "\nCurrent status: " + MAIN_CHANNEL
    except RequestException as error:
        print(error)
    except ValueError as error:
        print(error)
    return message


def silent_check(context):
    """Performs a silent check. Message is only sent if there is a problem. Also updates stats in chat description."""
    global consecutive_failures
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
        if consecutive_failures > 0:
            for chat_id in subscribed_chat_ids:
                context.bot.send_document(
                    chat_id=chat_id,
                    document=random.choice(RANDOM_POSITIVE_GIFS),
                    caption='✅ DoT is back up',
                )
            consecutive_failures = 0
        context.bot.set_chat_description(chat_id=MAIN_CHANNEL, description=get_stats())
    except dns.exception.DNSException as error:
        consecutive_failures += 1
        print('DNS error: ', error, 'message no.', consecutive_failures)
        if consecutive_failures == 2:
            for chat_id in subscribed_chat_ids:
                context.bot.send_document(
                    chat_id=chat_id,
                    document=random.choice(RANDOM_NEGATIVE_GIFS),
                    caption='🚨 DoT is unreachable!\n' + str(error),
                )


def stat(update, context):
    update.message.reply_text(get_stats())


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
    dispatcher.add_handler(CommandHandler("stat", stat))
    dispatcher.add_error_handler(error_callback)

    # Add repeating job to queue
    updater.job_queue.run_repeating(silent_check, CHECK_INTERVAL, 0)

    # Start the Bot
    updater.start_polling()

    # Block until you press Ctrl-C or the process receives SIGINT, SIGTERM or
    # SIGABRT. This should be used most of the time, since start_polling() is
    # non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
