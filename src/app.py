import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters, PicklePersistence
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup

from error_handler import error_callback
from models import *

from db_enums.game_states import GameStates
from configs.texts import Texts


## Constants
TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг
CREATE, PLAY, PREPARE, AWAIT, START, JOINING = range(6)

## SqlAlchemy objects
engine = create_engine('sqlite:///'+os.path.abspath(os.getcwd())+'\database.db', echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


## Telegram objects
bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN, persistence=PicklePersistence(filename='persistence_file'), use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_error_handler(error_callback)
# import sqlalchemy
# print(bot.get_me())   #Для отладки


## Настройка логирования
logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
logging.getLogger("telegram").setLevel(logging.INFO)
# logging.getLogger("sqlalchemy").setLevel(logging.INFO)
# logging.getLogger("urllib3").setLevel(logging.NOTSET)







def get_last_game(session,user):
    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user.id)\
        .order_by(Game.id.desc())\
        .first() # Получаем статус последней игры пользователя
    return last_game










#==================================================================================================#
#======================================  Прописываем фичи  ========================================#
#==================================================================================================#


def start(update, context):
    """
    Проверяем наличие пользователя
    Если есть, игнорируем
    Если нету, то:
    Спрашиваем имя
    Создаем пользователя
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session

    player = session.query(Player).filter_by(id=user.id).first()

    if not player:
        if user.is_bot == True:
            return # В жеппь ботов
        session.add(Player(id=int(user.id),name=user.username,points=0))
        session.commit() 
        update.message.reply_text(Texts.commandslist)
        logging.info(f"New user {user.id} added")
        return PREPARE
    else:
        update.message.reply_text(Texts.commandslist)
        session.close()
        return PREPARE



def create_game(update,context):
    """
    Проверяется на созданные и подключенные игры,
    Создается игра,
    Прописывается начальный статус
    Создатель присоединяется к игре
    Возвращается ID игры
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    if last_game == None or last_game.Game.state == GameStates.ended:
        new_game = Game(state=GameStates.begin,creator=user.id)                              # Новый объект игры
        session.add(new_game)                                                                # Создаем игру
        session.flush()                                                                      # Отправляем 
        session.add(Players2Game(game_id=new_game.id,player_id=user.id,position=0))          # Привязываем игрока к игре                                                                             # Отправляем
        update.message.reply_text(Texts.connectlink.format(game_id=str(new_game.id)))        # Присылаем создателю ID игры
        logging.info(f"User {user.id} create game")
        session.commit()
        return START
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(str(last_game.Game.id))))
        session.close()
        return START
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(Texts.already_in_game)
        session.close()
        return PLAY      # BUG: Тут надо точно кидать либо в игру, либо в ожидалку
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
        session.close()




def join_game(update,context):
    """
    Проверка статуса последней игры пользователя
    Спрашивает ID игры, если последняя закончилась
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    if last_game == None or last_game.Game.state == GameStates.ended:
        update.message.reply_text(Texts.try_to_join)
        return JOINING
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(last_game.Game.id)))
        session.close()
        return AWAIT
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(Texts.already_started)
        session.close()
        return PREPARE
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
        session.close()



def leave_joining(update,context):
    return PREPARE



def joining(update,context):
    """
    Проверка корректности ID игры
    Присоединение к игре
    Оповещение всех присоединившихся о том, кто зашел в лобби
    """
    user = update.message.from_user                 # get user data
    message = update.message                        # get user message
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    # Проверочки на левый ID игры
    try:
        int(message.text)
    except:
        message.reply_text(Texts.unable_to_connect)   # Не буквами
        return

    game_to_connect = session.query(Game).filter_by(id=message.text).first()

    if game_to_connect == None:
        message.reply_text(Texts.unable_to_connect)   # Не фуфло
        return
    if game_to_connect.state != GameStates.begin:
        message.reply_text(Texts.unable_to_connect)   # Не устаревший
        return


    
    # Выставляем очередность
    previous_player = session.query(Players2Game).filter_by(game_id=message.text).first()
    if previous_player == None:
        position = 0
    else:
        position = previous_player.position + 1

    # Добавляем игрока в игру
    if last_game == None or last_game.Game.state == GameStates.ended:
        session.add(Players2Game(game_id=message.text,player_id=user.id,position=position))     # Привязываем игрока к игре
        session.flush()                                                                         # Отправляем
        update.message.reply_text(Texts.succesfully_connected)                                  # Текст успеха
    else:
        message.reply_text(Texts.unable_to_connect)
        return PREPARE


    # Оповещаем участников
    players = session.query(Players2Game).filter_by(game_id=message.text).all()
    session.commit()
    for player in players:
        bot.send_message(chat_id=player.player_id, text=f"Игрок {user.name} присоединился!")
    logging.info(f"User {user.id} join game")
    return AWAIT




def begin_game(update,context):
    """
    Проверяем количество игроков
    Переводим игру в статус "in_progress"
    Раздаем всем игрокам равное количество рандомных карточек 
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game


    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id)).all()
    if len(players) < 3:  # Для игры нужно минимум трое
        update.message.reply_text(Texts.unable_to_begin)
        session.close()
    elif players == None:
        update.message.reply_text(Texts.unable_to_begin)
        session.close()
    else:
        game_to_end = session.query(Game).filter_by(id=last_game.Game.id).first()
        game_to_end.state = GameStates.in_progress
        cards = session.query(Cards).all()
        cards_set = set()
        for card in cards:
            cards_set.add(card.id)

        hand_size = len(cards_set) // len(players)

        for player in players:
            for i in range(hand_size):
                session.add(Hands(
                    player_id=player.player_id,
                    game_id=str(last_game.Game.id),
                    card_id=str(cards_set.pop())
                ))
                session.commit()

        for player in players:
            bot.send_message(chat_id=player.player_id, text=f"Карты раскиданы, игра началась!")

        return secret_card(update,context)
        



def secret_card(update,context):
    """
    Рассылаем всем игрокам сообщение о том, чей ход
    Присылаем всем их набор карточек
    Переводим в стейт, где дадим ему шанс прислать номер карточки
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id))
    last_turn = session.query(Turn).filter_by(game_id=str(last_game.Game.id))

    # Определяем чей ход
    if last_turn == None:
        current_player = players.filter_by(position=0).first()
    else:
        players_in_game = players.count()
        previous_player_position = players.filter_by(player_id=last_turn.players2game_id).first().position
        current_player_position = 0
        if previous_player_position < players_in_game:
            current_player_position = previous_player_position + 1
        elif previous_player_position == players_in_game:
            current_player_position = 0

        current_player = players.filter_by(position=current_player_position).first()

    current_player_name = session.query(Player).filter_by(id=current_player.player_id).first().name

    # Рассылаем инфу о ходящем
    for player in players.all():
        bot.send_message(chat_id=player.player_id, text=f"Ходит {current_player_name}")

    # Рассылаем наборы карточек, которые должны переключаться
    for player in player.all():
        player_cards = session.query(Hands).filter_by(game_id=last_game.Game.id, player_id=player.id, turn_id=None)
        # Кнопочки
        keyboard = [[InlineKeyboardButton("<", callback_data='<'),
                     InlineKeyboardButton(">", callback_data='>')],
                    [InlineKeyboardButton("Выбрать", callback_data='choose')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        bot.send_message(chat_id=player.player_id, text="Выберите картинку:")
        


def next_card(update,context):
    """
    Действие при нажатии на кнопку '>'
    Получаем предыдущее сообщение и меняем картинку на следующую из последних 5 карточек
    Как понять, какая картинка была в сообщении? Можно по URL!
    """
    
    keyboard = [[InlineKeyboardButton("<", callback_data='<'),
                     InlineKeyboardButton(">", callback_data='>')],
                    [InlineKeyboardButton("Выбрать", callback_data='choose')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    bot.edit_message_text(text='Выберите картинку:',
                            reply_markup=reply_markup,
                            chat_id=query.message.chat_id,
                            message_id=query.message.message_id)
    pass

def previous_card(update,context):
    """
    Действие при нажатии на кнопку '<'
    Получаем предыдущее сообщение и меняем картинку на предыдущую из последних 5 карточек
    """
    pass

def choose_card(update,context):
    """
    Действие при нажатии на кнопку 'Выбрать карту'
    """
    pass




def secret_word(update,context):
    """
    Получаем номер карточки и сохраняем
    Переводим в стейт, где спрашиваем секретное слово
    """
    pass

def turn(update,context):
    """
    Получаем секретное слово и сохраняем
    Рассылаем всем игрокам секретное слово
    Переводим в стейт ожидания
    """
    pass

def card(update,context):
    """
    Эта функция должна быть доступна в стейте ожидания, но работать только когда загадано секретное слово
    Предлагается выбрать свою карточку, соответствующую секретному слову
    Когда выставляется карта, на ней прописывается признак хода
    Когда выбираешь карточку - всем отображается сообщение о том что ты поставил карту
    когда последний поставил карточку - всем отображается реальный результат и очки
    Следующий ведущий переходит в стейт игры
    Остальные в ожидание
    """
    pass





def leave_game(update,context):
    """
    Отсоединяет пользователя от игры
    Завершает игру
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game



    if last_game == None or last_game.Game.state == GameStates.ended:
        update.message.reply_text(Texts.not_in_game)
        session.close()
        return PREPARE
    elif last_game.Game.state in (GameStates.begin,GameStates.in_progress):
        players = session.query(Players2Game).filter_by(game_id=last_game.Game.id).all()
        game_to_end = session.query(Game).filter_by(id=last_game.Game.id).first()
        game_to_end.state = GameStates.ended
        leaver_name = str(session.query(Player).filter_by(id=user.id).first().name)
        for player in players:
            bot.send_message(chat_id=player.player_id, text=Texts.game_ended_notification.format(player_id=leaver_name))
        logging.info(f"User {user.id} leave game")
        session.commit()
        return PREPARE
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")







def unknown_message(update,context):
    """
    Удаляет непонятные сообщения
    """
    bot.delete_message(chat_id=update.message.from_user.id,
               message_id=update.message.message_id)
    bot.sendMessage(chat_id=update.message.chat_id, text=Texts.commandslist)






def unknown_command(update,context):
    """
    Удаляет непонятные команды
    """
    bot.delete_message(chat_id=update.message.from_user.id,
               message_id=update.message.message_id)
    bot.sendMessage(chat_id=update.message.chat_id, text=Texts.commandslist)





#==================================================================================================#
#==================================================================================================#
#==================================================================================================#










def main():
    ## Вставляем фичу в обработчик
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={

            PREPARE:[
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game),
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            JOINING:[
                    CommandHandler('leave',leave_joining),
                    MessageHandler(Filters.text, joining)
                    ],

            START:  [
                    CommandHandler('begin', begin_game),
                    CommandHandler('leave',leave_game),
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            AWAIT:  [
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game),
                    CommandHandler('leave',leave_game),
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            PLAY:   [
                    CommandHandler('start', start),
                    CommandHandler('leave',leave_game),
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ]

        },

        fallbacks=[CommandHandler('cancel', leave_game)], 
        persistent=True, 
        name='persistention'
    )
    dispatcher.add_handler(conv_handler)

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку

if __name__ == '__main__':
    main()