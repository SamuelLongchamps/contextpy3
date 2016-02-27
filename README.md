# ContextPy3
Python3 port of the ContextPy library implementing Context-Oriented Programming as Layer-In-Class

The goal of this project is to port the ContextPy library to Python 3 and improve it to be as pythonic as possible 
and meet most PEP. Exceptions are :

* Use of CamelCase in both classes and methods name
* Access to protected members for specific library purposes

Also, this library has for purpose to serve as a basis for behavioral enhancements in the future. Feel free to fork 
and contribute!

# Original library
The original library for Python 2 can be found [here](https://www.hpi.uni-potsdam.de/hirschfeld/trac/Cop/wiki/ContextPy) (Hasso 
Plattner Institut) and [here](https://pypi.python.org/pypi/ContextPy/) (PyPi).

# About Context-Oriented Programming
Originally proposed by Robert Hirschfeld & al. ([see this article](http://www.jot.fm/issues/issue_2008_03/article4/))
, Context-Oriented Programming allows for dynamic activation of layers with which methods can provide specialized 
behavior. Each partial method defined can provide specialized behavior for a contextual state based on the 
combination of activated and deactivated layers. The goal is to easily and dynamically change the behavior of an 
application based on any computationnally available information that can be used to activate or deactivate layers.