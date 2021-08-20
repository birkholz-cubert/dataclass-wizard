import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from timeit import timeit
from typing import Optional, TypeVar, Dict, Any, List, Union, NamedTuple

import dataclass_factory
import pytest
from dataclasses_json import DataClassJsonMixin
from jsons import JsonSerializable

from dataclass_wizard import JSONWizard
from dataclass_wizard.class_helper import create_new_class
from dataclass_wizard.utils.string_conv import to_snake_case
from dataclass_wizard.utils.type_conv import as_datetime


log = logging.getLogger(__name__)


@dataclass
class MyClass:
    my_ledger: Dict[str, Any]
    the_answer_to_life: Optional[int]
    people: List['Person']
    is_enabled: bool = True


@dataclass
class MyClassDJ(DataClassJsonMixin):
    my_ledger: Dict[str, Any]
    the_answer_to_life: Optional[int]
    # spent a long time debugging the issue: `dataclasses-json` doesn't
    # seem to support List[ClassType] (unsure how to fix)
    # people: List[Person]
    people: List[Dict[str, Any]]
    is_enabled: bool = True


@dataclass
class Person:
    name: 'Name'
    age: int
    birthdate: datetime
    # dataclass-factory doesn't support Literals
    # gender: Literal['M', 'F', 'N/A']
    gender: str
    occupation: Union[str, List[str]]
    # dataclass-factory doesn't support DefaultDict
    # hobbies: DefaultDict[str, List[str]] = field(
    #     default_factory=lambda: defaultdict(list))
    hobbies: Dict[str, List[str]] = field(
        default_factory=lambda: defaultdict(list))


class Name(NamedTuple):
    """A person's name"""
    first: str
    last: str
    salutation: Optional[str] = 'Mr.'


# Model for `dataclass-wizard`
WizType = TypeVar('WizType', MyClass, JSONWizard)
# Model for `jsons`
JsonsType = TypeVar('JsonsType', MyClass, JsonSerializable)
# Model for `dataclasses-json`
DJType = TypeVar('DJType', MyClass, DataClassJsonMixin)
# Factory for `dataclass-factory`
factory = dataclass_factory.Factory()

MyClassWizard: WizType = create_new_class(
    MyClass, (MyClass, JSONWizard), 'Wizard',
    attr_dict=vars(MyClass).copy())
# MyClassDJ: DJType = create_new_class(
#     MyClass, (MyClass, DataClassJsonMixin), 'DJ')
MyClassJsons: JsonsType = create_new_class(
    MyClass, (MyClass, JsonSerializable), 'Jsons')


@pytest.fixture(scope='session')
def data():
    return {
        'my_ledger': {
            'Day 1': 'some details',
            'Day 17': ['a', 'sample', 'list']
        },
        'the_answer_to_life': '42',
        'people': [
            {
                'name': ('Roberto', 'Fuirron'),
                'age': 21,
                'birthdate': '1950-02-28T17:35:20Z',
                'gender': 'M',
                'occupation': ['sailor', 'fisher'],
                'hobbies': {'M-F': ('chess', '123', 'reading'), 'Sat-Sun': ['parasailing']}
            },
            {
                'name': ('Janice', 'Darr', 'Dr.'),
                'age': 45,
                # `jsons` doesn't support this format (not sure how to fix?)
                # 'birthdate': '1971-11-05 05:10:59',
                'birthdate': '1971-11-05T05:10:59Z',
                'gender': 'F',
                'occupation': 'Dentist'
            }
        ]
    }


def parse_iso_format(data):
    return as_datetime(data)


iso_format_schema = dataclass_factory.Schema(
    parser=parse_iso_format,
    serializer=datetime.isoformat
)

factory.schemas = {
    datetime: iso_format_schema
}


def test_load(data, n):
    g = globals().copy()
    g.update(locals())

    # Result: 3.728
    log.info('dataclass-wizard     %f',
             timeit('MyClassWizard.from_dict(data)', globals=g, number=n))

    # Result: 1.927
    log.info('dataclass-factory    %f',
             timeit('factory.load(data, MyClass)', globals=g, number=n))

    # Result: 20.990
    log.info('dataclasses-json     %f',
             timeit('MyClassDJ.from_dict(data)', globals=g, number=n))

    # these ones took a long time xD
    # Result: 101.533
    log.info('jsons                %f',
             timeit('MyClassJsons.load(data)', globals=g, number=n))

    # Result: 173.349
    log.info('jsons (strict)       %f',
             timeit('MyClassJsons.load(data, strict=True)', globals=g, number=n))

    # Assert the dataclass instances have the same values for all fields.

    c1 = MyClassWizard.from_dict(data)
    c2 = factory.load(data, MyClass)
    c3 = MyClassDJ.from_dict(data)
    c4 = MyClassJsons.load(data)

    # Really can't do a direct equality check because it's all over the place.
    # For example, `dataclass-factory` de-serializes NamedTuple sub-classes as
    # tuples. That's a bit odd, because our annotated type is clearly a NamedTuple
    # subclass (Name).
    # assert c1.__dict__ == c2.__dict__  == c3.__dict__ == c4.__dict__


def test_dump(data, n):

    c1 = MyClassWizard.from_dict(data)
    c2 = factory.load(data, MyClass)
    c3 = MyClassDJ.from_dict(data)
    c4 = MyClassJsons.load(data)

    g = globals().copy()
    g.update(locals())

    # Result: 4.150
    log.info('dataclass-wizard     %f',
             timeit('c1.to_dict()', globals=g, number=n))

    # Result: 4.878
    log.info('dataclass-factory    %f',
             timeit('factory.dump(c2, MyClass)', globals=g, number=n))

    # Result: 16.106
    log.info('dataclasses-json     %f',
             timeit('c3.to_dict()', globals=g, number=n))

    # Result: 69.602
    log.info('jsons                %f',
             timeit('c4.dump()', globals=g, number=n))

    # Result: 60.502
    log.info('jsons (strict)       %f',
             timeit('c4.dump(strict=True)', globals=g, number=n))

    # Assert the dict objects which are the result of `to_dict` are all equal.

    # Need this step because our lib converts field names to camel-case
    # by default.
    c1_dict = {to_snake_case(f): fval for f, fval in c1.to_dict().items()}
    # I tried to make the formats equal, but then I gave up midway. Probably not
    # worth the effort tbh. The other important difference is how NamedTuple's
    # are converted. `dataclass-factory` already loads them as tuples, so it
    # also dumps them as tuples. But in our case we dump as NamedTuple, because
    # technically NamedTuple is still JSON-serializable (its a tuple in the end)
    #
    # for person in c1_dict['people']:
    #     person['birthdate'] = person['birthdate'].replace('Z', '+00:00', 1)

    # assert c1_dict == factory.dump(c2, MyClass) == c3.to_dict() == c4.dump()
