import logging
import re

from text_fns import process_text, TextResult
from CovidAPI import fetch_data_from_API, get_twitter_link, get_best_resource_for, sync_resource

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.ext import ConversationHandler, CallbackQueryHandler, PicklePersistence

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ParseMode
from PIL import Image
import telegram
import os
import pytesseract
import cv2
import numpy as np
import re
from regex_cities import cities_reg

BEGINMSG = "Hi. Welcome to Covid Relief Bot"

MENU, GET_LOCATION = range(2)

logging.basicConfig(format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s', level = logging.INFO)
logger = logging.getLogger(__name__)

def start(update, context):
    update.message.reply_text(
        BEGINMSG,
        #reply_markup = ReplyKeyboardMarkup(
        #    [['Oxygen']
        #     #['Oxygen Bed'], ['Medicine'], ['Plasma'], ['Ambulance'], ['Exit']
        #     ],
        #    one_time_keyboard=True,
        #    resize_keyboard=True
        #),
    )

def exit_convo(update, context):
    start(update, context)
    return MENU

def handle_menu(update, context):
    resource = update.message.text
    context.user_data['resource_wanted'] = resource
    update.message.reply_text("Please enter city")
    return GET_LOCATION

def fetch_info(update, context):
    if 'resource_wanted' not in context.user_data:
        return exit_convo(update, context)
    resource = context.user_data['resource_wanted']
    location = update.message.text
    #update.message.reply_text(fetch_data_from_API(resource, location))
    res_list = fetch_data_from_API(resource, location)
    for resource in res_list:
        context.bot.send_message(chat_id=update.message.chat_id, text=resource, parse_mode = ParseMode.MARKDOWN)
    return exit_convo(update, context)

def preprocess_img(img):
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kernel = np.ones((1, 1), np.uint8)
    #img = cv2.dilate(img, kernel, iterations=1)
    #img = cv2.erode(img, kernel, iterations=1)
    # cv2.medianBlur(img, 3)
    img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    #img = cv2.GaussianBlur(thresh, (5,5), 0)
    #img = cv2.medianBlur(img,5)
    return img

def handle_text(update, context):
    text = update.message.text
    result = TextResult.from_text(text)
    if(result.msg_type == "resource"):
        sync_resource(result)
    elif (result.msg_type == "request"):
        get_best_resource_for(result)

def handle_photo(update, context):
    print(update)
    for img_dict in update.message['photo'][-1:]:
        file_id = img_dict['file_id']
        imgfile = context.bot.get_file(file_id)
        img_path = imgfile.download()
        image = cv2.imread(img_path)
        text = pytesseract.image_to_string(preprocess_img(image))
        reply = TextResult.from_text(
            text +
            (" " + update.message.text if update.message.text is not None else "") +
            (" " + update.message['caption'] if update.message.caption is not None else "")
        ).generate_reply()

        if reply != "":
            update.message.reply_text(reply, parse_mode = ParseMode.MARKDOWN)
        os.remove(img_path)

def handle_tweet_request(update, context):
    print("handle_tweet_request", update)
    try:
        if len(context.args) == 0:
            text_to_process = update["message"]["reply_to_message"]["text"]
        else:
            text_to_process = " ".join(context.args)
        text_ret = TextResult.from_text(text_to_process)  #process_text(update["message"]["reply_to_message"]["text"])
        location, resources = text_ret.location, text_ret.resources
        #tweet_link = get_twitter_link(text_ret.location, text_ret.resources)
        #_, _, resources, tags, location = process_text(text_to_process, True)
        if location == []:
            location = ["delhi"]
        tweet_link = get_twitter_link(location, resources)
        if tweet_link == "":
            update.message.reply_text("Couldn\'t find resources or city name")
        else:
            update.message.reply_text(text = "[Tweets for {}]({})".format(" ".join(resources + location), tweet_link), parse_mode = ParseMode.MARKDOWN)
    except Exception as e:
        print(e)
        update.message.reply_text("Please send the command as a reply to a message for which you would like twitter leads")
        
def error(update, context):
    """Log Errors caused by Updates."""
    print(context.error)
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    import json
    with open('config.json') as fp:
        config = json.load(fp)
    persistence = PicklePersistence(filename='conversationbot')
    updater = Updater(config["API_TOKEN"], use_context=True, persistence=persistence)
    dp = updater.dispatcher
    
    # Add Handlers
    dp.add_handler(CommandHandler("tweets", handle_tweet_request, pass_args = True))
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(MessageHandler(Filters.text, handle_text))

    login_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MENU: [
                #MessageHandler(Filters.regex('^(Oxygen)$'), handle_menu),
                MessageHandler(Filters.photo, handle_photo),
                #MessageHandler(Filters.regex('^(Oxygen Bed)$'), handle_menu),
                #MessageHandler(Filters.regex('^(Medicine)$'), handle_menu),
                #MessageHandler(Filters.regex('^(Plasma)$'), handle_menu),
                #MessageHandler(Filters.regex('^(Ambulance)$'), handle_menu)
            ],
            GET_LOCATION: [MessageHandler(Filters.text, fetch_info)],
        },
        fallbacks=[MessageHandler(Filters.regex('.*'), exit_convo)]
    )

    #dp.add_handler(login_handler)
    
    # log all errors
    dp.add_error_handler(error)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
