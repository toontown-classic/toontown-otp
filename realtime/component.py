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
