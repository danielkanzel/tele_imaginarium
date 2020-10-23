# -*- coding: utf-8 -*-

from sqlalchemy import Column, Integer, String, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from db_enums.game_states import GameStates

Base = declarative_base()

class Game(Base):
    __tablename__ = "game"
    id = Column(Integer, primary_key=True)
    creator = Column(String)
    state = Column(Enum(GameStates))
    players2game = relationship("Players2Game",back_populates="game")

class Player(Base):
    __tablename__ = "player"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    points = Column(Integer)
    players2game = relationship("Players2Game", back_populates="player")

class Players2Game(Base):
    __tablename__ = "players2game"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('game.id'))
    player_id = Column(Integer, ForeignKey('player.id'))
    position = Column(Integer)
    points = Column(Integer)
    game = relationship("Game",back_populates="players2game")
    player = relationship("Player",back_populates="players2game")
    turn = relationship("Turn",back_populates="players2game")

class Turn(Base):
    __tablename__ = "turn"
    id = Column(Integer, primary_key=True)
    players2game_id = Column(Integer, ForeignKey('players2game.id')) 
    game_id = Column(Integer, ForeignKey('game.id'))
    phrase = Column(String)
    players2game = relationship("Players2Game", back_populates="turn")

class Hands(Base):
    __tablename__ = "hands"
    id = Column(Integer, primary_key=True)
    players2game_id = Column(Integer, ForeignKey('players2game.id'))
    card_id = Column(Integer, ForeignKey('cards.id'))       # Линк к карте, позволяет контролировать ренж карт
    turn_id = Column(Integer, ForeignKey('turn.id'))        # Линк к ходу, заполняется, когда карта кладется на стол
    voters = Column(String)

class Cards(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True)
    path = Column(String)