import os

import numpy as np
import pandas as pd

from vivarium.framework import randomness
from vivarium.framework.util import from_yearly, to_yearly


class NonCRNTestPopulation:

    configuration_defaults = {
        'population': {
            'age_start': 0,
            'age_end': 100,
            'population_size': 100,
        },
        'input_data': {
            'location': "Kenya",
        }
    }

    def setup(self, builder):
        self.config = builder.configuration
        self.randomness = builder.randomness.get_stream('population_age_fuzz')
        columns = ['age', 'sex', 'location', 'alive', 'entrance_time', 'exit_time']
        self.population_view = builder.population.get_view(columns)

        builder.population.initializes_simulants(self.generate_test_population,
                                                 creates_columns=columns)

        builder.event.register_listener('time_step', self.age_simulants)

    def generate_test_population(self, pop_data):
        age_start = pop_data.user_data.get('age_start', self.config.population.age_start)
        age_end = pop_data.user_data.get('age_end', self.config.population.age_end)
        location = self.config.input_data.location

        population = _non_crn_build_population(pop_data.index, age_start, age_end, location,
                                               pop_data.creation_time, pop_data.creation_window, self.randomness)
        self.population_view.update(population)

    def age_simulants(self, event):
        population = self.population_view.get(event.index, query="alive == 'alive'")
        population['age'] += event.step_size / pd.Timedelta(days=365)
        self.population_view.update(population)


class TestPopulation(NonCRNTestPopulation):
    def setup(self, builder):
        super().setup(builder)
        self.age_randomness = builder.randomness.get_stream('age_initialization', for_initialization=True)
        self.register = builder.randomness.register_simulants

    def generate_test_population(self, pop_data):
        age_start = pop_data.user_data.get('age_start', self.config.population.age_start)
        age_end = pop_data.user_data.get('age_end', self.config.population.age_end)
        age_draw = self.age_randomness.get_draw(pop_data.index)
        if age_start == age_end:
            age = age_draw * (pop_data.creation_window / pd.Timedelta(days=365)) + age_start
        else:
            age = age_draw * (age_end - age_start) + age_start

        core_population = pd.DataFrame({'entrance_time': pop_data.creation_time,
                                        'age': age.values}, index=pop_data.index)
        self.register(core_population)

        location = self.config.input_data.location
        population = _build_population(core_population, location, self.randomness)
        self.population_view.update(population)


def _build_population(core_population, location, randomness_stream):
    index = core_population.index

    population = pd.DataFrame(
        {'age': core_population['age'],
         'entrance_time': core_population['entrance_time'],
         'sex': randomness_stream.choice(index, ['Male', 'Female'], additional_key='sex_choice'),
         'alive': pd.Series('alive', index=index).astype(
             pd.api.types.CategoricalDtype(categories=['alive', 'dead', 'untracked'], ordered=False)),
         'location': location,
         'exit_time': pd.NaT, },
        index=index)
    return population


def _non_crn_build_population(index, age_start, age_end, location, creation_time, creation_window, randomness_stream):
    if age_start == age_end:
        age = randomness_stream.get_draw(index) * (creation_window / pd.Timedelta(days=365)) + age_start
    else:
        age = randomness_stream.get_draw(index)*(age_end - age_start) + age_start

    population = pd.DataFrame(
        {'age': age,
         'sex': randomness_stream.choice(index, ['Male', 'Female'], additional_key='sex_choice'),
         'alive': pd.Series('alive', index=index).astype(
             pd.api.types.CategoricalDtype(categories=['alive', 'dead', 'untracked'], ordered=False)),
         'location': location,
         'entrance_time': creation_time,
         'exit_time': pd.NaT, },
        index=index)
    return population


def build_table(value, year_start, year_end, columns=('age', 'year', 'sex', 'value')):
    value_columns = columns[3:]
    if not isinstance(value, list):
        value = [value]*len(value_columns)

    if len(value) != len(value_columns):
        raise ValueError('Number of values must match number of value columns')

    rows = []
    for age in range(0, 140):
        for year in range(year_start, year_end+1):
            for sex in ['Male', 'Female', 'Both']:
                r_values = []
                for v in value:
                    if v is None:
                        r_values.append(np.random.random())
                    elif callable(v):
                        r_values.append(v(age, sex, year))
                    else:
                        r_values.append(v)
                rows.append([age, year, sex] + r_values)
    return pd.DataFrame(rows, columns=['age', 'year', 'sex'] + list(value_columns))


def make_dummy_column(name, initial_value):
    class DummyColumnMaker:
        def setup(self, builder):
            self.population_view = builder.population.get_view([name])
            builder.population.initializes_simulants(self.make_column,
                                                     creates_columns=[name])

        def make_column(self, pop_data):
            self.population_view.update(pd.Series(initial_value, index=pop_data.index, name=name))

        def __repr__(self):
            return f"dummy_column(name={name}, initial_value={initial_value})"
    return DummyColumnMaker()


def get_randomness(key='test', clock=lambda: pd.Timestamp(1990, 7, 2), seed=12345, for_initialization=False):
    return randomness.RandomnessStream(key, clock, seed=seed, for_initialization=for_initialization)


def reset_mocks(mocks):
    for mock in mocks:
        mock.reset_mock()

def metadata(file_path):
    return {'layer': 'override', 'source': os.path.realpath(file_path)}
