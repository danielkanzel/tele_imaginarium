import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telegram import Update, User

from error_handler import error_callback
from models import *

from db_enums.game_states import GameStates
from configs.texts import Texts


## Constants
TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг
BEGIN, CREATE, PLAY, PREPARE, AWAIT, START = range(6)

## SqlAlchemy objects
engine = create_engine('sqlite:///'+os.path.abspath(os.getcwd())+'\database.db', echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


## Telegram objects
bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN, use_context=True)
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






def get_user_info(update, context):
    user_id = update.message.from_user.id
    user_data = context.user_data
    user_message = update.message.text
    data = {}
    for variable in ['user_id', "user_data", "user_message"]:
        data[variable] = eval(variable)
    return data

def get_last_game(session,user_data):
    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user_data.get('user_id'))\
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
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()


    def check_existing_user(session, telegram_id):
        """
        Проверки на наличие пользователя
        """
        # TODO Добавить всякие проверки на бота
        player = session.query(Player).filter_by(id=telegram_id).first()
        if not player:
            logging.info(f"User {user_data.get('user_id')} first time")
            return False
        else:
            logging.info(f"User {user_data.get('user_id')} exist")
    session.close()

    if check_existing_user(session, user_data.get('user_id')) == False:
        update.message.reply_text(Texts.hello)
        return BEGIN
    else:
        update.message.reply_text(Texts.commandslist)
        return PREPARE

        

def create_user(update, context):
    """
    Создание пользователя, после получения его имени
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()

    session.add(Player(id=int(user_data.get('user_id')),name=user_data.get('user_message'),points=0))
    session.commit() 
    # reply and log
    update.message.reply_text(Texts.commandslist)
    logging.info(f"User {user_data.get('user_id')} added")
    # next state
    return PREPARE
    



def create_game(update,context):
    """
    Проверяется на созданные и подключенные игры,
    Создается игра,
    Прописывается начальный статус
    Создатель присоединяется к игре
    Возвращается ID игры
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()
    # get last game
    last_game = get_last_game(session,user_data)

    if last_game == None or last_game.Game.state == GameStates.ended:
        new_game = Game(state=GameStates.begin,creator=user_data.get('user_id'))                        # Новый объект игры
        session.add(new_game)                                                                           # Создаем игру
        session.flush()                                                                                 # Отправляем 
        session.add(Players2Game(game_id=new_game.id,player_id=user_data.get('user_id'),position=0))    # Привязываем игрока к игре                                                                             # Отправляем
        update.message.reply_text(Texts.connectlink.format(game_id=str(new_game.id)))                    # Присылаем создателю ID игры
        logging.info(f"User {user_data.get('user_id')} create game")
        session.commit()
        return START
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(str(last_game.Game.id))))
        session.close()
        return START
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(Texts.already_in_game)
        session.close()
        return PLAY
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
        session.close()




def join_game(update,context):
    """
    Получение данных пользователя
    Получение последней игры пользователя
    Проверка статуса последней игры пользователя
    Присоединение к игре, если она в статусе начинающейся
    Оповещение всех присоединившихся о том, кто зашел в лобби
    """
    # get user data
    user_data = get_user_info(update, context)
    try:
        game_id = user_data.get('user_message').split(" ")[1] # Отрезаем команду /join
    except:
        update.message.reply_text(Texts.unable_to_connect)
        return
    # init DB session
    session = Session()
    # get last game
    last_game = get_last_game(session,user_data)
    # get game to connect info
    game_to_connect = session.query(Game).filter_by(id=game_id).first()        


    # Проверочки на левый ID игры
    try:
        int(game_id)
    except:
        update.message.reply_text(Texts.unable_to_connect)   # Не цифрой
        return
    if game_to_connect == None:
        update.message.reply_text(Texts.unable_to_connect)   # Не пустой
        return
    if game_to_connect.state != GameStates.begin:
        update.message.reply_text(Texts.unable_to_connect)   # Не фуфло
        return


    if last_game == None or last_game.Game.state == GameStates.ended:
        previous_player = session.query(Players2Game).filter_by(game_id=game_id).first()
        if previous_player == None:
            position = 0
        else:
            position = previous_player.position + 1
        session.add(Players2Game(game_id=game_id,player_id=user_data.get('user_id'),position=position))        # Привязываем игрока к игре
        session.flush()                                                                                 # Отправляем
        update.message.reply_text(Texts.succesfully_connected)                                          # Текст успеха
        players = session.query(Players2Game).filter_by(game_id=game_id).all()
        connected_player = session.query(Player).filter_by(id=user_data.get('user_id')).first()
        session.commit()
        for player in players:
            bot.send_message(chat_id=player.player_id, text=f"Игрок {connected_player.name} присоединился!")
        logging.info(f"User {user_data.get('user_id')} join game")

        
        return AWAIT
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(last_game.Game.id)))
        session.close()
        return AWAIT
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(Texts.already_started)
        session.close()
        return PLAY
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")
        session.close()







def start_game(update,context):
    """
    Проверяем количество игроков
    Переводим игру в статус "in_progress"
    Раздаем всем игрокам равное количество рандомных карточек 
    """
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()
    # get last game
    last_game = get_last_game(session,user_data)


    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id)).all()
    if len(players) < 3:  # check number of players
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
                    turn_id=str(cards_set.pop())
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
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()
    # get last game
    last_game = get_last_game(session,user_data)

    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id))

    last_turn = session.query(Turn).filter_by(game_id=str(last_game.Game.id))

    print("""
    ===============================================
    Here we go
    +++++++++++++++++++++++++++++++++++++++++++++++
    """)

    if last_turn == None:
        current_player = players.filter_by(position=0)
    else:
        previous_player_id = session.query()
        current_player = session.query()

    for player in players.all():
        bot.send_message(chat_id=player.player_id, text=f"Карты раскиданы, игра началась!")



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
    # get user data
    user_data = get_user_info(update, context)
    # init DB session
    session = Session()
    # get last game
    last_game = get_last_game(session,user_data)



    if last_game == None or last_game.Game.state == GameStates.ended:
        update.message.reply_text(Texts.not_in_game)
        session.close()
        return PREPARE
    elif last_game.Game.state in (GameStates.begin,GameStates.in_progress):
        players = session.query(Players2Game).filter_by(game_id=last_game.Game.id).all()
        game_to_end = session.query(Game).filter_by(id=last_game.Game.id).first()
        game_to_end.state = GameStates.ended
        leaver_name = str(session.query(Player).filter_by(id=user_data.get('user_id')).first().name)
        for player in players:
            bot.send_message(chat_id=player.player_id, text=Texts.game_ended_notification.format(player_id=leaver_name))
        logging.info(f"User {user_data.get('user_id')} leave game")
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

            BEGIN: [
                    CommandHandler('start', start), 
                    MessageHandler(Filters.text, create_user)
                    ],

            PREPARE:[
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game),
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            START:  [
                    CommandHandler('begin', start_game),
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

        fallbacks=[CommandHandler('cancel', leave_game)]
    )
    dispatcher.add_handler(conv_handler)

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку

if __name__ == '__main__':
    main()