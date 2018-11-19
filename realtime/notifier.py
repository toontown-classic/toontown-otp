"""
 * Copyright (C) Caleb Marshall - All Rights Reserved
 * Written by Caleb Marshall <anythingtechpro@gmail.com>, September 2nd, 2018
 * Licensing information can found in 'LICENSE', which is part of this source code package.
"""

import coloredlogs
import logging


class LoggingNotifier(object):

    def __init__(self, category):
        # create a new Python logging object in which will actually
        # log the messages to stdout...
        self.__logger = logging.getLogger(category)

        # setup the colored logging module for this new logger
        # object so we can have colored logs...
        coloredlogs.install(level='INFO', logger=self.__logger)

    def info(self, message):
        self.__logger.info(message)
        return True

    def debug(self, message):
        self.__logger.debug(message)
        return True

    def warning(self, message):
        self.__logger.warning(message)

    def error(self, message):
        self.__logger.error(message)

class LoggingNotify(object):

    def __init__(self):
        self.__categories = {}

    def new_category(self, category):
        notifier = self.__categories.get(category)
        if not notifier:
            notifier = LoggingNotifier(category)
            self.__categories[category] = notifier

        return notifier

notify = LoggingNotify()
