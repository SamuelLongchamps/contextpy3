# License (MIT License)
# 
# Copyright (c) 2007-2008 Christian Schubert and Michael Perscheid
# michael.perscheid@hpi.uni-potsdam.de, http://www.hpi.uni-potsdam.de/swa/
#
# Port to Python 3 and improvements by Samuel Longchamps (2016)
# samuel.longchamps@usherbrooke.ca
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import sys
from threading import local

__all__ = ['Layer']
__all__ += ['activeLayer', 'activeLayers', 'inactiveLayer', 'inactiveLayers']
__all__ += ['proceed']
__all__ += ['before', 'after', 'around', 'base']
__all__ += ['globalActivateLayer', 'globalDeactivateLayer']

__version__ = "2.0"

# tuple with layers that are always active
_baseLayers = (None,)


class _MyTLS(local):
    """
    Thread-local storage used for thread-specific layer state conservation
    """
    def __init__(self):
        super(_MyTLS, self).__init__()
        self.context = None
        self.activelayers = ()

_tls = _MyTLS()


class Layer(object):
    """
    Representation of a COP Layer as an object
    """
    def __init__(self, name=None):
        """
        Constructor for a COP layer

        :param name: (Optional) Name of the layer
        """
        self.__name = name

    def getIdentifier(self):
        """
        :return: Identifier for this layer
        """
        return self.__name or hex(id(self))

    def __str__(self):
        return "<layer {}>".format(self.getIdentifier())

    def __repr__(self):
        args = []
        if self.__name is not None:
            args.append('name="{}"'.format(self.__name))
        return "layer({})".format(", ".join(args))

    # TODO: Check what it is used for
    def getEffectiveLayers(self, activelayers):
        return activelayers


class _LayerManager(object):
    """
    Base manager for COP layers which takes care of entering and exiting states
    """
    def __init__(self, layers):
        self._layers = layers
        self._oldLayers = ()

    def _getActiveLayers(self):
        return self._oldLayers

    def __enter__(self):
        self._oldLayers = _tls.activelayers
        _tls.activelayers = tuple(self._getActiveLayers())

    def __exit__(self, exc_type, exc_value, exc_tb):
        _tls.activelayers = self._oldLayers


class _LayerActivationManager(_LayerManager):
    """
    Specialized manager for COP layers which adds layers to the active layers
    """
    def _getActiveLayers(self):
        # TODO: Get rid of code duplication
        return [layer for layer in self._oldLayers if layer not in self._layers] + self._layers


class _LayerDeactivationManager(_LayerManager):
    """
    Specialized manager for COP layers which removes layers from the active layers
    """
    def _getActiveLayers(self):
        return [layer for layer in self._oldLayers if layer not in self._layers]


def activeLayer(layer):
    return _LayerActivationManager([layer])


def inactiveLayer(layer):
    return _LayerDeactivationManager([layer])


def activeLayers(*layers):
    return _LayerActivationManager(list(layers))


def inactiveLayers(*layers):
    return _LayerDeactivationManager(list(layers))


class _Advice(object):
    """
    Type of invokator which can be chained and will automatically order calls depending on the implementation
    """
    def __init__(self, func, nextFct):
        self._func = func or None
        self._nextFct = nextFct

    def _invoke(self, context, args, kwargs):
        """
        Invoke a function using a context object.

        Binding is required only if kind of instance method, class or static method.
        Otherwise, invoke as normal Python function
        """
        return self._func(*args, **kwargs) if context[0] is None and context[1] is None else \
            self._func.__get__(context[0], context[1])(*args, **kwargs)

    def __call__(self, context, args, kwargs):
        raise NotImplementedError

    @classmethod
    def createChain(cls, methods):
        if not methods:
            return _Stop(None, None)
        method, when = methods[0]
        return when(method, cls.createChain(methods[1:]))


class _Before(_Advice):
    def __call__(self, context, args, kwargs):
        self._invoke(context, args, kwargs)
        return self._nextFct(context, args, kwargs)


class _Around(_Advice):
    def __call__(self, context, args, kwargs):
        backup = _tls.context
        _tls.context = context
        context[2] = self._nextFct
        result = self._invoke(context, args, kwargs)
        _tls.context = backup
        return result


class _After(_Advice):
    def __call__(self, context, args, kwargs):
        result = self._nextFct(context, args, kwargs)
        kwargsWithResult = dict(__result__=result, **kwargs)
        return self._invoke(context, args, kwargsWithResult)


class _Stop(_Advice):
    def __call__(self, context, args, kwargs):
        raise Exception(
            "called proceed() in innermost function, this probably means that you don't have a base method "
            "(`around` advice in None layer) or the base method itself calls proceed()")


def proceed(*args, **kwargs):
    context = _tls.context
    return context[2](context, args, kwargs)


def _true(activelayers):
    return True


class _LayeredMethodInvocationProxy(object):
    __slots__ = ("_descriptor", "_inst", "_cls")

    def __init__(self, descriptor, inst, cls):
        self._descriptor = descriptor
        self._inst = inst
        self._cls = cls

    def __call__(self, *args, **kwargs):
        activelayers = _baseLayers + _tls.activelayers
        advice = self._descriptor._cache.get(activelayers) or self._descriptor.cacheMethods(activelayers)

        context = [self._inst, self._cls, None]
        result = advice(context, args, kwargs)
        return result

    def getMethods(self):
        return self._descriptor.methods

    def setMethods(self, methods):
        self._descriptor.methods = methods

    def getName(self):
        return self._descriptor.methods[-1][1].__name__

    def registerMethod(self, f, when=_Around, layer_=None, guard=_true):
        self._descriptor.registerMethod(f, when, layer_, guard)

    def unregisterMethod(self, f, layer_=None):
        self._descriptor.unregisterMethod(f, layer_)

    methods = property(getMethods, setMethods)
    __name__ = property(getName)


class _LayeredMethodDescriptor(object):
    def __init__(self, methods):
        self._methods = methods
        self._cache = {}

    def _clearCache(self):
        for key in self._cache.keys():
            self._cache.pop(key, None)

    def cacheMethods(self, activelayers):
        layers = list(activelayers)
        for layer_ in activelayers:
            # TODO: Check what this does since getEffectiveLayers just returns the same list
            if layer_ is not None:
                layers = layer_.getEffectiveLayers(layers)

        methods = []
        for currentlayer in activelayers:
            for lmwgm in self._methods:
                if lmwgm[0] is currentlayer and lmwgm[3](activelayers):
                    methods.append((lmwgm[1], lmwgm[2]))
        methods = list(reversed(methods))  # TODO: Look up why the order is important for the list "methods"

        self._cache[activelayers] = result = _Advice.createChain(methods)
        return result

    def setMethods(self, methods):
        self._methods[:] = methods
        self._clearCache()

    def getMethods(self):
        return list(self._methods)

    def registerMethod(self, f, when=_Around, layer_=None, guard=_true, methodName=""):
        # TODO: Lookup why these are useful
        if methodName == "":
            methodName = f.__name__
        if hasattr(when, "when"):
            when = when.when

        assert isinstance(layer_, (Layer, type(None)))
        assert issubclass(when, _Advice)

        self.methods = self.methods + [
            (layer_, f, when, guard, methodName)]

    def unregisterMethod(self, f, layer_=None):
        self.methods = [lmwgm for lmwgm in self._descriptor.methods if
                        lmwgm[1] is not f or lmwgm[0] is not layer_]

    methods = property(getMethods, setMethods)

    def __get__(self, inst, cls=None):
        return _LayeredMethodInvocationProxy(self, inst, cls)

    # Used only for functions (no binding or invocation proxy needed)
    def __call__(self, *args, **kwargs):
        activelayers = _baseLayers + _tls.activelayers
        advice = self._cache.get(activelayers) or self.cacheMethods(activelayers)

        # 2x None to identify: do not bound this function
        context = [None, None, None]
        result = advice(context, args, kwargs)
        return result


def createlayeredmethod(baseMethod, partial):
    return _LayeredMethodDescriptor([(None, baseMethod, _Around, _true)] + partial) if baseMethod else \
           _LayeredMethodDescriptor(partial)


# Needed for a hack to get the name of the class/static method object
class _dummyClass:
    pass


def getMethodName(method):
    # Bind the method to a dummy class to retrieve the original name for class or static methods
    return method.__get__(None, _dummyClass).__name__ if type(method) in (classmethod, staticmethod) else \
           method.__name__


def __common(layer_, guard, when):
    assert isinstance(layer_, (Layer, type(None))), "layer_ argument must be a layer instance or None"
    assert callable(guard), "guard must be callable"
    assert issubclass(when, _Advice)

    vars = sys._getframe(2).f_locals

    def decorator(method):
        methodName = getMethodName(method)
        currentMethod = vars.get(methodName)
        if issubclass(type(currentMethod), _LayeredMethodDescriptor):
            # Append the new method
            currentMethod.registerMethod(method, when, layer_, guard, methodName)
        else:
            currentMethod = createlayeredmethod(currentMethod, [(layer_, method, when, guard, methodName)])
        return currentMethod

    return decorator


def before(layer_=None, guard=_true):
    return __common(layer_, guard, _Before)


def around(layer_=None, guard=_true):
    return __common(layer_, guard, _Around)


def after(layer_=None, guard=_true):
    return __common(layer_, guard, _After)


def base(method):
    # look for the current entry in the __dict__ (class or module)
    vars = sys._getframe(1).f_locals
    methodName = getMethodName(method)
    currentMethod = vars.get(methodName)
    if issubclass(type(currentMethod), _LayeredMethodDescriptor):
        # add the first entry of the layered method with the base entry
        currentMethod.methods += [(None, method, _Around, _true)]
        return currentMethod
    return method

# TODO: Verify for what purpose this exists
before.when = _Before
around.when = _Around
after.when = _After


def globalActivateLayer(layer):
    global _baseLayers
    if layer in _baseLayers:
        raise ValueError("layer is already active")
    _baseLayers += (layer,)
    return _baseLayers


def globalDeactivateLayer(layer):
    global _baseLayers
    if layer not in _baseLayers:
        raise ValueError("layer is not active")
    _baseLayers = tuple(l for l in _baseLayers if l is not layer)
    return _baseLayers
