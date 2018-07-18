import time

import numpy as np
import pandas as pd


class NonCRNBasePopulation:

    configuration_defaults = {
        'population': {
            'age_start': 0,
            'age_end': 100,
        }
    }

    def setup(self, builder):
        self.config = builder.configuration
        self.randomness = builder.randomness.get_stream('population_age_fuzz')

        columns_created = ['age', 'sex', 'alive', 'entrance_time', 'exit_time']
        builder.population.initializes_simulants(self.generate_test_population, creates_columns=columns_created)

        self.population_view = builder.population.get_view(columns_created)

        builder.event.register_listener('time_step', self.age_simulants)

    def generate_test_population(self, pop_data):
        age_start = pop_data.user_data.get('age_start', self.config.population.age_start)
        age_end = pop_data.user_data.get('age_end', self.config.population.age_end)

        if age_start == age_end:
            age = (age_start
                   + self.randomness.get_draw(pop_data.index) * (pop_data.creation_window / pd.Timedelta(days=365)))
        else:
            age = age_start + self.randomness.get_draw(pop_data.index) * (age_end - age_start)

        population = pd.DataFrame(
            {'age': age,
             'sex': self.randomness.choice(pop_data.index, ['Male', 'Female'], additional_key='sex_choice'),
             'alive': pd.Series('alive', index=pop_data.index),
             'entrance_time': pop_data.creation_time},
            index=pop_data.index)

        self.population_view.update(population)

    def age_simulants(self, event):
        population = self.population_view.get(event.index, query="alive == 'alive'")
        population['age'] += event.step_size / pd.Timedelta(days=365)
        self.population_view.update(population)


class BasePopulation(NonCRNBasePopulation):

    configuration_defaults = {
        'population': {
            'age_start': 0,
            'age_end': 100,
        },
        'randomness': {
            'key_columns': ['entrance_time', 'age']
        }
    }

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

        population = pd.DataFrame({'entrance_time': pop_data.creation_time,
                                   'age': age.values}, index=pop_data.index)
        self.register(population)

        pop_data['sex'] = self.randomness.choice(pop_data.index, ['Male', 'Female'], additional_key='sex_choice')
        pop_data['alive'] = 'alive'

        self.population_view.update(population)


class Mortality:

    configuration_defaults = {
        'mortality': {
            'mortality_rate': 0.01,
            'life_expectancy': 80,
        }

    }

    def setup(self, builder):
        self.config = builder.configuration.mortality
        self.population_view = builder.population.get_view(['alive'], query="alive == 'alive'")
        self.randomness = builder.randomness

        self.mortality_rate = builder.value.register_rate_producer('mortality_rate', source=self.base_mortality_rate)

        builder.event.register_listener('time_step', self.determine_deaths)

    def base_mortality_rate(self, index):
        return pd.Series(self.config.mortality_rate, index=index)

    def determine_deaths(self, event):
        effective_rate = self.mortality_rate(event.index)
        effective_probability = 1 - np.exp(-effective_rate)
        draw = np.random.random(size=len(event.index))
        affected_simulants = draw < effective_probability
        self.population_view.update(pd.Series('dead', index=event.index[affected_simulants]))


class Observer:

    def setup(self, builder):
        self.life_expectancy = builder.configuration.mortality.life_expectancy
        self.population_view = builder.population.get_view(['age', 'alive'])

        builder.value.register_value_modifier('metrics', self.metrics)
        builder.event.register_listener('post_setup', self.start_clock)
        builder.event.register_listener('simulation_end', self.stop_clock)

    def start_clock(self, event):
        self.start_time = time.time()

    def stop_clock(self, event):
        self.end_time = time.time()

    def metrics(self, index, metrics):
        metrics['run_time'] = self.end_time - self.start_time

        pop = self.population_view.get(index)
        metrics['total_population_alive'] = len(pop[pop.alive == 'alive'])
        metrics['total_population_dead'] = len(pop[pop.alive == 'dead'])

        metrics['years_of_life_lost'] = (self.life_expectancy - pop.age[pop.alive == 'dead']).sum()

        return metrics
