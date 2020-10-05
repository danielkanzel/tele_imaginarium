

class Texts():
    commandslist = """/create - создать новую игру,
/join - присоединиться к игре
/begin - запустить созданную игру
/leave - выйти из игры
"""

    try_to_join = """Введи ID игры"""

    connectlink = """
Игра создана, ID {game_id}. 
Отправь ID друзьям, чтобы они присоединились"""

    remindconnectlink = """
Игра уже создана, ID {game_id}. 
Отправь ID друзьям, чтобы они присоединились"""

    already_in_game = "Нельзя создать игру, пока не закончена предыдущая"

    succesfully_connected = "Вы присоединились к игре, ожидайте начала"

    already_started = "Нельзя присоединиться к запущенной игре"

    not_in_game = "Вы не в игре"

    leave_success = "Вы вышли из игры"

    game_ended_notification = """Игрок {player_id} завершил игру
Нажмите /leave, чтобы выйти из завершенной игры"""

    unable_to_connect = "Невозможно подключиться к этой игре"

    unable_to_begin = "Слишком мало игроков"