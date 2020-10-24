# -*- coding: utf-8 -*-

import telegram
from telegram import InputMediaPhoto
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters, CallbackQueryHandler,PicklePersistence
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

# from mongopersistence import DBPersistence


## Constants
TOKEN = os.environ.get('TOKEN')
PORT = int(os.environ.get('PORT', '8443'))
PREPARE, JOINING, START, AWAIT, PLAY = range(5)

## SqlAlchemy objects
engine = create_engine('sqlite:///'+os.path.abspath(os.getcwd())+'\database.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

## Настройка логирования
logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        level=logging.DEBUG
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

def get_current_game(session,user):
    last_game = session.query(Game,Players2Game)\
        .join(Players2Game, Players2Game.game_id == Game.id)\
        .filter_by(player_id=user.id)\
        .filter(Game.state==GameStates.in_progress)\
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
            name=str(user.name),
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

    # Проверка на максимальное количество игроков
    # Непроверенная фича
    players = session.query(Players2Game).filter_by(game_id=message.text).all()
    if len(players) >= 7:
        message.reply_text("Максимальное число игроков 7")
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
    
    current_game = session.query(Game).filter_by(id=last_game.Game.id).first()

    # Проверка на повторный бегин
    if current_game.state == GameStates.in_progress:
        session.close()
        return


    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id)).all()
    if len(players) < 3:  # Для игры нужно минимум трое
        update.message.reply_text(Texts.unable_to_begin)
        session.close()
    elif players == None: # Хз когда вызывается, возможно излишняя защита
        update.message.reply_text(Texts.unable_to_begin)
        session.close()
    else:
        # Прописываем статус in progress
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
            bot.send_message(
                chat_id=player.player_id, 
                text=f"Карты раскиданы, игра началась!"
                )

        return secret_card(update,context)
        



def secret_card(update,context):
    """
    Рассылаем всем игрокам сообщение о том, чей ход
    Присылаем всем их набор карточек
    Переводим в стейт, где дадим ему шанс прислать номер карточки
    """
    user = (update.message.from_user or update.callback_query.message.chat)      # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)         # get last game

    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id))
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()



    # Определяем чей ход
    if last_turn == None:
        current_player = players.filter_by(position=0).first()
    else:
        players_in_game = players.count()
        previous_player_position = players.filter_by(id=last_turn.players2game_id).first().position
        if previous_player_position < players_in_game - 1:
            current_player_position = previous_player_position + 1
        elif previous_player_position == players_in_game - 1:
            current_player_position = 0

        current_player = players.filter_by(position=current_player_position).first()

    # Создаем ход
    session.add(Turn(
                    players2game_id=current_player.id,
                    game_id=str(last_game.Game.id)
                ))
    
    session.commit()

    # Рассылаем инфу о ходящем
    current_player_name = session.query(Player).filter_by(id=current_player.player_id).first().name
    for player in players.all():
        bot.send_message(
            chat_id=player.player_id, 
            text=f"Загадывает {current_player_name}"
            )

    # Готовим выбиралку для ходящего
    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)

    first_card_image = session.query(Cards).filter_by(id=cards_on_hands[0].card_id).first().path

    # Кнопочки
    keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                    InlineKeyboardButton(">", callback_data='next_card')],
                [InlineKeyboardButton("Выбрать", callback_data='choose')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logging.info(f"User {user.id} got cards")

    bot.send_photo(
        chat_id=current_player.player_id, 
        photo=first_card_image, 
        reply_markup=reply_markup,
        caption=f"1/{str(cards_on_hands.count())}"
            )

    session.close()
    return PLAY
        


def next_card(update,context):
    """
    Действие при нажатии на кнопку '>'
    Получаем предыдущее сообщение и меняем картинку на следующую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

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
    if current_card_order == cards_on_hands.count():
        next_card = cards_on_hands[0]
        next_card_order = 1
    else:
        next_card = cards_on_hands[current_card_order]
        next_card_order = current_card_order + 1

    next_card = session.query(Cards).filter_by(id=next_card.card_id).first()

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                InlineKeyboardButton(">", callback_data='next_card')]]

    if last_turn.players2game_id == current_player.id:
        keyboard.append([InlineKeyboardButton("Загадать эту карту", callback_data='choose')])
    elif last_turn.phrase != None:
        keyboard.append([InlineKeyboardButton("Предложить эту карту к фразе", callback_data='suggest')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=next_card.path,
            caption=f'{str(next_card_order)}/{update.callback_query.message.caption.split("/")[1]}'
        ),
        reply_markup=reply_markup
    )

    session.close()
    

# Как разрулить проблему, когда надо переключать карты по конкретной игре, во всех выбиралках? - Удалять старые выбиралки, тщательно вычищать лог игры

def previous_card(update,context):
    """
    Действие при нажатии на кнопку '<'
    Получаем предыдущее сообщение и меняем картинку на предыдущую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

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
        previous_card = cards_on_hands[cards_on_hands.count()-1]
        previous_card_order = 5
    else:
        previous_card = cards_on_hands[current_card_order-2]
        previous_card_order = current_card_order - 1

    previous_card = session.query(Cards).filter_by(id=previous_card.card_id).first()

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                InlineKeyboardButton(">", callback_data='next_card')]]
    if last_turn.players2game_id == current_player.id:
        keyboard.append([InlineKeyboardButton("Загадать эту карту", callback_data='choose')])
    elif last_turn.phrase != None:
        keyboard.append([InlineKeyboardButton("Предложить эту карту к фразе", callback_data='suggest')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=previous_card.path,
            caption=f'{str(previous_card_order)}/{update.callback_query.message.caption.split("/")[1]}'
        ),
        reply_markup=reply_markup
    )

    session.close()


def choose_card(update,context):
    """
    Действие при нажатии на кнопку 'Выбрать карту'
    Получаем номер карточки и сохраняем
    Переводим в стейт, где спрашиваем секретное слово
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

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
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()
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
    last_game = get_current_game(session,user)      # get current game

    # Получаем секретное слово и сохраняем
    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()
    last_turn.phrase = update.message.text
    session.commit()

    # Рассылаем всем игрокам секретное слово
    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id))
    for player in players.all():
        if player.player_id == user.id:
            bot.send_message(
                chat_id=player.player_id, 
                text="Ожидание действий остальных игроков"
                )
        else:
            cards_on_hands = session.query(Hands).filter_by(
                players2game_id=player.id, 
                turn_id=None
                ).order_by(Hands.id.desc()).limit(5)
            first_card_image = session.query(Cards).filter_by(id=cards_on_hands[0].card_id).first().path


            # Кнопочки
            keyboard = [[InlineKeyboardButton("<", callback_data='previous_card'),
                            InlineKeyboardButton(">", callback_data='next_card')],
                        [InlineKeyboardButton("Предложить эту карту к фразе", callback_data='suggest')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logging.info(f"User {user.id} got cards")

            bot.send_photo(
                chat_id=player.player_id, 
                photo=first_card_image, 
                reply_markup=reply_markup,
                caption=f"""1/{str(cards_on_hands.count())}
Игрок {str(user.username)} загадал {str(last_turn.phrase)}"""
                    )
            

    session.close()
    
    # Переводим в стейт ожидания
    return AWAIT



def suggest_card(update,context):
    """
    # Эта функция должна быть доступна всегда, но работать только когда загадано секретное слово
    # Предлагается выбрать свою карточку, соответствующую секретному слову
    # Когда выставляется карта, на ней прописывается признак хода
    # когда последний поставил карточку - всем отображается реальный результат и очки
    # Следующий ведущий переходит в стейт игры
    # Остальные в ожидание
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

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

    # Отрисовываем ответ (обновляем голосовалку)
    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=current_card_image,
            caption=f"{update.callback_query.message.caption.splitlines()[1]}, а вы предложили эту карту" 
        )
    )

    # Присваиваем карту к ходу
    current_card.turn_id = last_turn.id
    session.commit()

    # Получаем полный список карт на столе
    players = session.query(Players2Game).filter_by(game_id=str(last_game.Game.id)).all()

    player_ids = []
    for player in players:
        player_ids.append(str(player.id)) # Говнятина TODO

    cards_on_table = session.query(Hands)\
        .filter(Hands.players2game_id.in_(player_ids))\
        .filter(Hands.turn_id == last_turn.id)\
        .all()


    if len(players) == len(cards_on_table):
        for player in players:
            if player.id == last_turn.players2game_id:
                continue   

            first_card = session.query(Hands).filter_by(turn_id=last_turn.id).order_by(Hands.card_id.desc()).first()

            first_card_image = session.query(Cards).filter_by(id=first_card.card_id).first().path

            # Кнопочки
            keyboard = [[InlineKeyboardButton("<", callback_data='table_previous_card'),
                        InlineKeyboardButton(">", callback_data='table_next_card')]]

            card_owner = session.query(Players2Game).filter_by(id=first_card.players2game_id).first()

            if card_owner.id != player.id:
                keyboard.append([InlineKeyboardButton("Эту карту загадал ведущий", callback_data='vote')])

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


    
def next_card_table(update,context):
    """
    Действие при нажатии на кнопку '>'
    Получаем предыдущее сообщение и меняем картинку на следующую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

    # Получаем порядок карты среди последних 5
    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_table = session.query(Hands).filter_by(turn_id=last_turn.id).order_by(Hands.card_id.desc()).all()

    count_cards_on_table = session.query(Hands).filter_by(turn_id=last_turn.id).count()

    # Следующая карта
    if current_card_order == count_cards_on_table:
        next_card = cards_on_table[0]
        next_card_order = 1
    else:
        next_card = cards_on_table[current_card_order]
        next_card_order = current_card_order + 1

    next_card_path = session.query(Cards).filter_by(id=next_card.card_id).first().path

    keyboard = [[InlineKeyboardButton("<", callback_data='table_previous_card'),
                InlineKeyboardButton(">", callback_data='table_next_card')]]

    card_owner = session.query(Players2Game).filter_by(id=next_card.players2game_id).first()

    if card_owner.id != current_player.id:
        keyboard.append([InlineKeyboardButton("Эту карту загадал ведущий", callback_data='vote')])
 
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=next_card_path,
            caption=f'{str(next_card_order)}/{str(count_cards_on_table)}'
        ),
        reply_markup=reply_markup
    )

    session.close()
    

# Как разрулить проблему, когда надо переключать карты по конкретной игре, во всех выбиралках? - Удалять старые выбиралки, тщательно вычищать лог игры

def previous_card_table(update,context):
    """
    Действие при нажатии на кнопку '<'
    Получаем предыдущее сообщение и меняем картинку на предыдущую
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_table = session.query(Hands).filter_by(turn_id=last_turn.id).order_by(Hands.card_id.desc()).all()

    count_cards_on_table = session.query(Hands).filter_by(turn_id=last_turn.id).count()

    if current_card_order == 1:
        previous_card = cards_on_table[count_cards_on_table-1]
        previous_card_order = count_cards_on_table
    else:
        previous_card = cards_on_table[current_card_order-2]
        previous_card_order = current_card_order - 1

    previous_card_path = session.query(Cards).filter_by(id=previous_card.card_id).first().path

    keyboard = [[InlineKeyboardButton("<", callback_data='table_previous_card'),
                InlineKeyboardButton(">", callback_data='table_next_card')]]

    card_owner = session.query(Players2Game).filter_by(id=previous_card.players2game_id).first()

    if card_owner.id != current_player.id:
        keyboard.append([InlineKeyboardButton("Эту карту загадал ведущий", callback_data='vote')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=previous_card_path,
            caption=f'{str(previous_card_order)}/{str(count_cards_on_table)}'
        ),
        reply_markup=reply_markup
    )

    session.close()


def vote_card(update,context):
    """
    Действие при нажатии на кнопку 'Эту карту загадал ведущий'
    Получаем номер карточки и сохраняем
    Заменяем предыдущее сообщение на 
    """
    user = update.callback_query.message.chat       # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

    # Записываем карту в БД
    current_card_order = int(update.callback_query.message.caption.split("/")[0])

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    current_player = session.query(Players2Game).filter_by(
        player_id=user.id, 
        game_id=last_game.Game.id
        ).first()

    cards_on_table = session.query(Hands).filter_by(turn_id=last_turn.id).order_by(Hands.card_id.desc()).all()

    current_card = cards_on_table[current_card_order - 1]

    if current_card.voters == None:
        current_card.voters = str(current_player.id)
    else:
        current_card.voters = f"{current_card.voters}, {str(current_player.id)}" 

    # Отправляем сообщение
    current_card_image = update.callback_query.message.photo[0].file_id

    update.callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=current_card_image,
            caption="Вы проголосовали за эту карту"
        )
    )

    session.commit()

    players = session.query(Players2Game).filter_by(game_id=last_game.Game.id).all()

    # Сбор голосов
    voted_cards = session.query(Hands).filter_by(turn_id=last_turn.id).filter(Hands.voters != None).all()

    all_votes = {}

    for card in voted_cards:
        for i in card.voters.split(", "):
            all_votes[i] = card.card_id

    turn_player = session.query(Players2Game).filter_by(id=last_turn.players2game_id).first()

    # Подсчет очков, если все голоса собраны
    if len(players)-1 == len(all_votes):


        turn_player_name = session.query(Player).filter_by(id=turn_player.player_id).first().name

        real_card = session.query(Hands).filter_by(
                players2game_id=turn_player.id,
                turn_id=last_turn.id
                ).first()

        res_text = f"""Итоги этого хода:
{turn_player_name} загадал {last_turn.phrase}
=====================================
"""

        # Если все угадали
        if all(x == real_card.card_id for x in all_votes.values()):
            for player in players:
                if player.id == turn_player.id:
                    continue
                player.points = int(player.points or 0) + 3

            session.commit()

            res_text += """
Все угадали карту, всем, кроме ведущего, по 3 балла"""

        else:
            # Если никто не угадал
            if all(x != real_card.card_id for x in all_votes.values()):
                res_text += f"""
Ведущего {turn_player_name} никто не угадал, поэтому ему 0 баллов"""
            # Если угадал не только лишь каждый
            else:
                turn_player.points = int(turn_player.points or 0) + 3
                session.commit()
                res_text += f"""
Ведущий {turn_player_name} получает 3 балла"""
            for vote in all_votes:
                voter = session.query(Players2Game).filter_by(id=vote).first()
                voter_name = session.query(Player).filter_by(id=voter.player_id).first().name
                # Если игрок угадал ведущего
                if all_votes[vote] == real_card.id:
                    voter.points = int(voter.points or 0) + 3
                    session.commit()
                    res_text += f"""
{voter_name} проголосовал за карту ведущего {turn_player_name}. {voter_name} получает 3 балла"""
                # Если игрок не угадал ведущего
                else:
                    voted_card = session.query(Hands).filter_by(
                        card_id=all_votes[vote],
                        turn_id=last_turn.id).first()
                    voted = session.query(Players2Game).filter_by(id=voted_card.players2game_id).first()
                    voted_name = session.query(Player).filter_by(id=voted.player_id).first().name
                    voted.points = int(voted.points or 0) + 1
                    session.commit() 
                    res_text += f"""
{voter_name} проголосовал за карту игрока {voted_name}. {voted_name} получает 1 балл"""

        # Рассылка итогов {'14': 8, '15': 8}
        for player in players:
            bot.send_message(chat_id=player.player_id, text=res_text)

    if turn_player.position < len(players) - 1:
        next_player_position = turn_player.position + 1
    elif turn_player.position == len(players) - 1:
        next_player_position = 0

    current_player = session.query(Players2Game).filter_by(
        game_id=str(last_game.Game.id),
        position=next_player_position
        ).first()

    cards_on_hands = session.query(Hands).filter_by(
        players2game_id=current_player.id, 
        turn_id=None
        ).order_by(Hands.id.desc()).limit(5)

    if cards_on_hands.count() == 0:
        for player in players:
            bot.send_message(
                chat_id=player.player_id, 
                text="""Карты закончились.
Нажмите /status, чтобы посмотреть счет.
Нажмите /leave, чтобы выйти из завершенной игры."""
                )
    else:
        bot.send_message(
                chat_id=current_player.player_id, 
                text=f"Нажми /turn для начала своего хода"
                )
    session.commit()


        



def turn(update,context):
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game
    
    current_game = session.query(Game).filter_by(id=last_game.Game.id).first()

    last_turn = session.query(Turn).filter_by(game_id=last_game.Game.id).order_by(Turn.id.desc()).first()

    # Проверка на незаконченный turn, прожать получится, только если все проголосовали
    players = session.query(Players2Game).filter_by(game_id=last_game.Game.id).all()

    voted_cards = session.query(Hands).filter_by(turn_id=last_turn.id).filter(Hands.voters != None).all()

    all_votes = {}

    for card in voted_cards:
        for i in card.voters.split(", "):
            all_votes[i] = card.card_id

    if len(players)-1 != len(all_votes):
        session.close()
        return

    # Проверка на не того человека
    turn_player = session.query(Players2Game).filter_by(id=last_turn.players2game_id).first()

    if turn_player.position < len(players) - 1:
        next_player_position = turn_player.position + 1
    elif turn_player.position == len(players) - 1:
        next_player_position = 0

    next_player = session.query(Players2Game).filter_by(
        game_id=str(last_game.Game.id),
        position=next_player_position
        ).first()

    if str(next_player.player_id) != str(user.id):
        session.close()
        return

    return secret_card(update,context)
             
        
def status(update,context):
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_current_game(session,user)      # get current game

    players = session.query(Players2Game)\
        .filter_by(game_id=last_game.Game.id)\
        .order_by(Players2Game.points.desc())\
        .all()

    res_text = """Количество очков у игроков на текущий момент:
=============================================
"""

    for player in players:
        player_name = session.query(Player).filter_by(id=player.player_id).first().name

        res_text += f"""
У игрока {player_name} - {str(player.points or 0)} б.
"""
    update.message.reply_text(res_text)




def leave_game(update,context):
    """
    Отсоединяет пользователя от игры
    Завершает игру
    """
    user = update.message.from_user                 # get user data
    session = Session()                             # init DB session
    last_game = get_last_game(session,user)      # get current game



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
    # bot.sendMessage(chat_id=update.message.chat_id, text=Texts.commandslist)





#==================================================================================================#
#==================================================================================================#
#==================================================================================================#






def main():
    ## Telegram objects
    bot = telegram.Bot(token=TOKEN)

    updater = Updater(
        token=TOKEN,
        # persistence=DBPersistence(),
        persistence=PicklePersistence(filename='persistence_file'), 
        use_context=True
        )

    updater.start_webhook(listen="0.0.0.0",
                      port=PORT,
                      url_path=TOKEN)
    updater.bot.set_webhook(f"https://danielkanzel.xyz/{TOKEN}")

    print("================================================== ВЕБХУКИ ВСТАЛИ")
    print(updater.bot.getWebhookInfo().to_dict())

    dispatcher = updater.dispatcher

    dispatcher.add_error_handler(error_callback)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={

            PREPARE:[
                    CommandHandler('create', create_game),
                    CommandHandler('join', join_game),
                    MessageHandler(Filters.text, unknown_message),
                    ],

            JOINING:[
                    CommandHandler('leave',leave_joining),
                    MessageHandler(Filters.text, joining)
                    ],

            START:  [
                    CommandHandler('begin', begin_game),
                    CommandHandler('leave',leave_game),
                    MessageHandler(Filters.text, start_turn)
                    ],

            AWAIT:  [
                    CommandHandler('status', status),
                    CommandHandler('turn', turn),
                    CommandHandler('leave',leave_game),
                    ],

            PLAY:   [
                    CommandHandler('status', status),
                    CommandHandler('leave',leave_game),
                    MessageHandler(Filters.regex(r'/.*'), unknown_command),
                    MessageHandler(Filters.text, start_turn),
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
    dispatcher.add_handler(CallbackQueryHandler(next_card_table, pattern="table_next_card"))
    dispatcher.add_handler(CallbackQueryHandler(previous_card_table, pattern="table_previous_card"))
    dispatcher.add_handler(CallbackQueryHandler(choose_card,pattern="choose"))
    dispatcher.add_handler(CallbackQueryHandler(suggest_card,pattern="suggest"))
    dispatcher.add_handler(CallbackQueryHandler(vote_card,pattern="vote"))

    print("================================================== ХАНДЛЕРЫ ПРОПИСАЛИСЬ")


    ## Запускаем мясорубку
    
    updater.idle()
    print("================================================== ОНО ДОЛЖНО НА ЭТОМ ЭТАПЕ РАБОТАТЬ")
    # updater.start_polling()
    # updater.idle()
    ## Вырубаем мясорубку
    # updater.stop()  # TODO автоматизировать выключалку


if __name__ == '__main__':
    main()