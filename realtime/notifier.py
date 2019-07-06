# Copyright (c) 2019, Caleb Marshall.
#
# This file is part of Toontown OTP.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# You should have received a copy of the MIT License
# along with Toontown OTP. If not, see <https://opensource.org/licenses/MIT>.

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
