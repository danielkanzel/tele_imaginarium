

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
        session.add(Player(id=int(user.id),name=user.username,points=0))
        session.commit() 
        update.message.reply_text(Texts.commandslist)
        logging.info(f"New user {user.id} added")
        return PREPARE
    else:
        update.message.reply_text(Texts.commandslist)
        session.close()
        return PREPARE