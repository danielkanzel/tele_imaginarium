import telegram
from telegram import InputMediaPhoto
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters, PicklePersistence, CallbackQueryHandler
import logging
import os
import random
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup

from error_handler import error_callback
from models import *

from db_enums.game_states import GameStates
from configs.texts import Texts


## Constants
TOKEN = '789364882:AAF6-OLy36xTCZB0Y3KQtK0pfZTUuRe56dM' # TODO Убрать в конфиг
CREATE, PLAY, PREPARE, AWAIT, START, JOINING, SECRET = range(7)

## SqlAlchemy objects
engine = create_engine('sqlite:///'+os.path.abspath(os.getcwd())+'\database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


## Telegram objects
bot = telegram.Bot(token=TOKEN)
updater = Updater(
    token=TOKEN, 
    persistence=PicklePersistence(filename='persistence_file'), 
    use_context=True
    )
dispatcher = updater.dispatcher
dispatcher.add_error_handler(error_callback)


## Настройка логирования
logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        level=logging.INFO
        )
logging.getLogger(__name__)
# logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)
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
            session.close()
            return # В жеппь ботов
        session.add(Player(
            id=int(user.id),
            name=user.username,
            points=0)
            )
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
        session.add(Players2Game(game_id=new_game.id,player_id=user.id,position=0))          # Привязываем игрока к игре
        update.message.reply_text(Texts.connectlink.format(game_id=str(new_game.id)))        # Присылаем создателю ID игры
        logging.info(f"User {user.id} create game")
        session.commit()
        return START
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(last_game.Game.id)))
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
    session.close()

    if last_game == None or last_game.Game.state == GameStates.ended:
        update.message.reply_text(Texts.try_to_join)
        return JOINING
    elif last_game.Game.state == GameStates.begin:
        update.message.reply_text(Texts.remindconnectlink.format(game_id=str(last_game.Game.id)))
        return AWAIT
    elif last_game.Game.state == GameStates.in_progress:
        update.message.reply_text(Texts.already_started)
        return PREPARE
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")



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
        session.close()
        return
    game_to_connect = session.query(Game).filter_by(id=message.text).first()

    if game_to_connect == None:
        message.reply_text(Texts.unable_to_connect)   # Не фуфло
        session.close()
        return
    if game_to_connect.state != GameStates.begin:
        message.reply_text(Texts.unable_to_connect)   # Не устаревший
        session.close()
        return


    
    # Выставляем очередность
    previous_player = session.query(Players2Game).filter_by(game_id=message.text).order_by(desc(Players2Game.position)).first()
    if previous_player == None:
        position = 0
    else:
        position = previous_player.position + 1

    # Добавляем игрока в игру
    if last_game == None or last_game.Game.state == GameStates.ended:
        session.add(Players2Game(
            game_id=message.text,
            player_id=user.id,
            position=position)
            )     # Привязываем игрока к игре
        session.flush()                                                                         # Отправляем
        update.message.reply_text(Texts.succesfully_connected)                                  # Текст успеха
    else:
        message.reply_text(Texts.unable_to_connect)
        session.close()
        return PREPARE


    # Оповещаем участников
    players = session.query(Players2Game).filter_by(game_id=message.text).all()
    session.commit()
    for player in players:
        bot.send_message(
            chat_id=player.player_id, 
            text=f"Игрок {user.name} присоединился!"
            )
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
    elif players == None: # Хз когда вызывается, возможно излишняя защита
        update.message.reply_text(Texts.unable_to_begin)
        session.close()
    else:
        # Статус in progress
        current_game = session.query(Game).filter_by(id=last_game.Game.id).first()
        current_game.state = GameStates.in_progress

        # Делим карты на всех, без остатка, в случайном порядке
        cards = session.query(Cards).all()
        cards_list = []
        for card in cards:
            cards_list.append(card.id)
        random.shuffle(cards_list)
        hand_size = len(cards_list) // len(players)

        for player in players:
            for i in range(hand_size):
                session.add(
                    Hands(
                        players2game_id=player.id,
                        card_id=cards_list.pop()
                        )
                    )

        # Загружаем вышеописанное в базу
        session.commit()

        # Уведомление на всех, что игра началась
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
    last_turn = session.query(Turn).filter_by(game_id=str(last_game.Game.id)).first()


    # Определяем чей ход
    if last_turn == None:
        current_player = players.filter_by(position=0).first()
    else:
        players_in_game = players.count()
        previous_player_position = players.filter_by(player_id=last_turn.players2game_id).first().position
        if previous_player_position < players_in_game:
            current_player_position = previous_player_position + 1
        elif previous_player_position == players_in_game:
            current_player_position = 0

        current_player = players.filter_by(position=current_player_position).first()

    # Создаем ход
    session.add(Turn(
                    players2game_id=current_player.player_id,
                    game_id=str(last_game.Game.id)
                ))
    
    session.commit()

    # Рассылаем инфу о ходящем
    current_player = session.query(Player).filter_by(id=current_player.player_id).first()
    for player in players.all():
        bot.send_message(
            chat_id=player.player_id, 
            text=f"Ходит {current_player.name}"
            )
        first_card = session.query(Hands).filter_by(
            players2game_id=player.id, 
            turn_id=None
            ).order_by(Hands.id.desc()).first()
        first_card_image = session.query(Cards).filter_by(id=first_card.card_id).first().path

        # Кнопочки
        keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                     InlineKeyboardButton(">", callback_data='next_card')]]
        if player.player_id == current_player.id:
            keyboard.append([InlineKeyboardButton("Выбрать", callback_data='choose')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        logging.info(f"User {user.id} got cards")

        bot.send_photo(
            chat_id=player.player_id, 
            photo=first_card_image, 
            reply_markup=reply_markup,
            caption="1/5"
            )

    session.close()
        


def next_card(update,context):
    """
    Действие при нажатии на кнопку '>'
    Получаем предыдущее сообщение и меняем картинку на следующую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    # Получаем порядок карты среди последних 5
    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)

    # Следующая карта
    if current_card_order == 5:
        next_card = cards_on_hands[0]
        next_card_order = 1
    else:
        next_card = cards_on_hands[current_card_order]
        next_card_order = current_card_order + 1

    next_card = session.query(Cards).filter_by(id=next_card.card_id).first()

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()

    keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                InlineKeyboardButton(">", callback_data='next_card')]]
    if last_turn.players2game_id == user.id:
        keyboard.append([InlineKeyboardButton("Загадать эту карту", callback_data='choose')])
    elif last_turn.phrase != None:
        keyboard.append([InlineKeyboardButton("Предложить эту карту к фразе", callback_data='suggest')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=next_card.path,
            caption=f'{str(next_card_order)}/5'
        ),
        reply_markup=reply_markup
    )
    session.close()
    pass

# Как разрулить проблему, когда надо переключать карты по конкретной игре, во всех выбиралках? - Удалять старые выбиралки, тщательно вычищать лог игры

def previous_card(update,context):
    """
    Действие при нажатии на кнопку '<'
    Получаем предыдущее сообщение и меняем картинку на предыдущую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)

    if current_card_order == 1:
        previous_card = cards_on_hands[4]
        previous_card_order = 5
    else:
        previous_card = cards_on_hands[current_card_order-2]
        previous_card_order = current_card_order - 1

    previous_card = session.query(Cards).filter_by(id=previous_card.card_id).first()

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()

    keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                InlineKeyboardButton(">", callback_data='next_card')]]
    if last_turn.players2game_id == user.id:
        keyboard.append([InlineKeyboardButton("Выбрать", callback_data='choose')])
    elif last_turn.phrase != None:
        keyboard.append([InlineKeyboardButton("Предложить эту карту к фразе", callback_data='suggest')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=previous_card.path,
            caption=f'{str(previous_card_order)}/5'
        ),
        reply_markup=reply_markup
    )
    session.close()
    pass

def choose_card(update,context):
    """
    Действие при нажатии на кнопку 'Выбрать карту'
    Получаем номер карточки и сохраняем
    Переводим в стейт, где спрашиваем секретное слово
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    # Записываем карту в БД
    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)

    current_card = cards_on_hands[current_card_order - 1]
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()
    current_card.turn_id = last_turn.id
    session.flush()
    


    # Отправляем сообщение
    current_card_image = update.callback_query.message.photo[0].file_id

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=current_card_image,
            caption="Теперь введите фразу:"
        )
    )

    session.commit()
    



def start_turn(update,context):
    """
    Получаем секретное слово и сохраняем
    Если секретное слово не вовремя - удаляем
    Рассылаем всем игрокам секретное слово и карточки
    Переводим в стейт ожидания
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    # Получаем секретное слово и сохраняем
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()
    last_turn.phrase = update.message.text
    session.commit()

    # Рассылаем всем игрокам секретное слово
    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id))
    for player in players.all():
        if player.player_id == user.id:
            bot.send_message(chat_id=player.player_id, text="Ожидание действий остальных игроков")
        else:
            bot.send_message(chat_id=player.player_id, text=f"Игрок {str(user.username)} загадал {str(last_turn.phrase)}")

    session.close()
    
    # Переводим в стейт ожидания
    return AWAIT

def suggest_card(update,context):
    """
    # Эта функция должна быть доступна в стейте ожидания, но работать только когда загадано секретное слово
    # Предлагается выбрать свою карточку, соответствующую секретному слову
    # Когда выставляется карта, на ней прописывается признак хода
    # когда последний поставил карточку - всем отображается реальный результат и очки
    # Следующий ведущий переходит в стейт игры
    # Остальные в ожидание
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)         # get last game

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()

    if not last_turn.phrase:
        return # Будет работать только с фразой

    # Получаем данные для отрисовки ответа
    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)    
    
    current_card = cards_on_hands[current_card_order - 1]
    current_card_image = session.query(Cards).filter_by(id=current_card.card_id).first().path

    # Присваем карту к ходу
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).first()
    current_card.turn_id = last_turn.id
    session.flush()

    # Получаем полный список карт на столе
    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id)).all()

    player_ids = []
    for player in players:
        player_ids.append(str(player.id))

    cards_on_table = session.query(Hands)\
        .filter(Hands.players2game_id.in_(player_ids))\
        .filter(Hands.turn_id != None)\
        .all() #Сложный фильтр, не факт что работает


    if len(cards_on_table) < len(players): # Если не все выложили карты
        return # Надо убирать голосовалку
    elif len(cards_on_table) == len(players): # Если все выложили карты
        for player in players:
            first_card = session.query(Hands).filter_by(
                players2game_id=player.id, 
                turn_id=None
                ).order_by(Hands.id.desc()).first()
            first_card_image = session.query(Cards).filter_by(id=first_card.card_id).first().path
            # Кнопочки
            keyboard = [[InlineKeyboardButton("<", callback_data='previous_card_table'),
                        InlineKeyboardButton(">", callback_data='next_card_table')]]
            if player.player_id == current_player.id:
                keyboard.append([InlineKeyboardButton("Выбрать", callback_data='choose_table')])
            reply_markup = InlineKeyboardMarkup(keyboard)

            bot.send_photo(
                chat_id=player.player_id, 
                photo=first_card_image, 
                reply_markup=reply_markup, 
                caption=f"1/{len(cards_on_table)}"
                )


        pass
    else:
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
            bot.send_message(
                chat_id=player.player_id, 
                text=Texts.game_ended_notification.format(player_id=leaver_name)
                )
        logging.info(f"User {user.id} leave game")
        session.commit()
        return PREPARE
    else:
        logging.debug(f"Unknown game {last_game.Game.id} state")







def unknown_message(update,context):
    """
    Удаляет непонятные сообщения
    """
    print("================================" + str(update.effective_message.message_id))
    # bot.delete_message(chat_id=update.message.from_user.id,
    #            message_id=update.message.message_id)
    # bot.sendMessage(chat_id=update.message.chat_id, text=Texts.commandslist)






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
                    MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            JOINING:[
                    CommandHandler('leave',leave_joining),
                    MessageHandler(Filters.text, joining)
                    ],

            START:  [
                    CommandHandler('begin', begin_game),
                    CommandHandler('leave',leave_game),
                    MessageHandler(Filters.text, start_turn)
                    # MessageHandler(Filters.text, unknown_message),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            SECRET: [
                    CommandHandler('leave',leave_game),
                    ],

            AWAIT:  [
                    # CommandHandler('create', create_game),
                    # CommandHandler('join', join_game),
                    # CommandHandler('begin', begin_game),
                    CommandHandler('leave',leave_game),
                    # MessageHandler(Filters.text, card),
                    # MessageHandler(Filters.regex(r'/.*'), unknown_command)
                    ],

            PLAY:   [
                    CommandHandler('leave',leave_game),
                    CommandHandler('turn',secret_card),
                    MessageHandler(Filters.regex(r'/.*'), start_turn)
                    # MessageHandler(Filters.text, unknown_message),
                    ]

        },

        fallbacks=[CommandHandler('cancel', leave_game)], 
        persistent=True, 
        name='persistention'
    )
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CallbackQueryHandler(next_card, pattern="next_card"))
    dispatcher.add_handler(CallbackQueryHandler(previous_card, pattern="previous_card"))
    dispatcher.add_handler(CallbackQueryHandler(choose_card,pattern="choose"))
    dispatcher.add_handler(CallbackQueryHandler(suggest_card,pattern="suggest"))

    ## Запускаем мясорубку
    updater.start_polling()
    updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку


if __name__ == '__main__':
    main()