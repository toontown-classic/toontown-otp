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

from realtime.notifier import notify


class Component(object):

    def setup(self):
        pass

    def shutdown(self):
        pass


class ComponentManager(object):
    notify = notify.new_category('ComponentManager')

    def __init__(self):
        self._components = []

    @property
    def components(self):
        return self._components

    def has_component(self, component):
        assert(isinstance(component, Component))
        return component in self._components

    def add_component(self, component):
        assert(isinstance(component, Component))
        if component in self._components:
            return

        self.notify.info('Starting component: %s...' % component.__class__.__name__)
        self._components.append(component)
        component.setup()

    def remove_component(self, component):
        assert(isinstance(component, Component))
        if component not in self._components:
            return

        self.notify.info('Shutting down component: %s...' % component.__class__.__name__)
        self._components.remove(component)
        component.shutdown()

    def shutdown(self):
        assert(len(self._components) > 0)
        for component in list(self._components):
            self.remove_component(component)
