from dataclasses import MISSING
from functools import wraps
from typing import Callable, Union

from .models import Extras, TypeInfo
from ..utils.function_builder import FunctionBuilder


def setup_recursive_safe_function(
    func: Callable = None,
    *,
    fn_name: Union[str, None] = None,
    is_generic: bool = False,
) -> Callable:
    """
    A decorator to ensure recursion safety and facilitate dynamic function generation
    with `FunctionBuilder`, supporting both generic and non-generic types.

    The decorated function can define the logic for dynamically generated functions.
    If `fn_name` is provided, the decorator assumes that the function generation
    context (e.g., `with fn_gen.function(...)`) has already been handled externally
    and will not apply it again.

    :param func: The function to decorate. If None, the decorator is applied with arguments.
    :type func: Callable, optional
    :param fn_name: A format string for dynamically generating function names, or None.
    :type fn_name: str, optional
    :param is_generic: Whether the function deals with generic types.
    :type is_generic: bool, optional
    :return: The decorated function with recursion safety and dynamic function generation.
    :rtype: Callable
    """

    if func is None:
        return lambda f: setup_recursive_safe_function(
            f, fn_name=fn_name, is_generic=is_generic
        )

    def _wrapper_logic(tp: TypeInfo, extras: Extras, _cls=None) -> str:
        """
        Shared logic for both class and regular methods. Ensures recursion safety
        and integrates `FunctionBuilder` to dynamically create functions.

        :param tp: The type or generic type being processed.
        :param extras: A context dictionary containing auxiliary information like
                       recursion guards and function builders.
        :type extras: dict
        :param _cls: The class context for class methods. Defaults to None.
        :return: The generated function call expression as a string.
        :rtype: str
        """
        cls = tp.args if is_generic else tp.origin
        recursion_guard = extras['recursion_guard']

        if (_fn_name := recursion_guard.get(cls)) is None:
            cls_name = extras['cls_name']
            tp_name = func.__name__.split('_', 2)[-1]

            # Generate the function name
            if fn_name:
                _fn_name = fn_name.format(cls_name=tp.name)
            else:
                _fn_name = (
                    f'_load_{cls_name}_{tp_name}_{tp.field_i}' if is_generic
                    else f'_load_{cls_name}_{tp_name}_{tp.name}'
                )

            recursion_guard[cls] = _fn_name

            # Retrieve the main FunctionBuilder
            main_fn_gen = extras['fn_gen']

            # Prepare a new FunctionBuilder for this function
            updated_extras = extras.copy()
            updated_extras['locals'] = _locals = {'cls': cls}
            updated_extras['fn_gen'] = new_fn_gen = FunctionBuilder()

            # Apply the decorated function logic
            if fn_name:
                # Assume `with fn_gen.function(...)` is already handled
                func(_cls, tp, updated_extras) if _cls else func(tp, updated_extras)
            else:
                # Apply `with fn_gen.function(...)` explicitly
                with new_fn_gen.function(_fn_name, ['v1'], MISSING, _locals):
                    func(_cls, tp, updated_extras) if _cls else func(tp, updated_extras)

            # Merge the new FunctionBuilder into the main one
            main_fn_gen |= new_fn_gen

        return f'{_fn_name}({tp.v()})'

    # Determine if the function is a class method
    # noinspection PyUnresolvedReferences
    is_class_method = func.__code__.co_argcount == 3

    if is_class_method:
        def wrapper_class_method(_cls, tp, extras) -> str:
            """
            Wrapper logic for class methods. Passes the class context to `_wrapper_logic`.

            :param _cls: The class instance.
            :param tp: The type or generic type being processed.
            :param extras: A context dictionary with auxiliary information.
            :type extras: dict
            :return: The generated function call expression as a string.
            :rtype: str
            """
            return _wrapper_logic(tp, extras, _cls)

        wrapper = wraps(func)(wrapper_class_method)
    else:
        wrapper = wraps(func)(_wrapper_logic)

    return wrapper


def setup_recursive_safe_function_for_generic(func: Callable) -> Callable:
    """
    A helper decorator to handle generic types using
    `setup_recursive_safe_function`.

    Parameters
    ----------
    func : Callable
        The function to be decorated, responsible for returning the
        generated function name.

    Returns
    -------
    Callable
        A wrapped function ensuring recursion safety for generic types.
    """
    return setup_recursive_safe_function(func, is_generic=True)