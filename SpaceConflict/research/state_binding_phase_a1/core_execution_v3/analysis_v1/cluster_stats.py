"""World-cluster paired bootstrap; fixed cohort includes zero-denominator worlds."""
import random
from collections import defaultdict
from functools import lru_cache


def quantile(values,p):
    values=sorted(values)
    if not values: return None
    x=(len(values)-1)*p; i=int(x); j=min(i+1,len(values)-1)
    return values[i]+(values[j]-values[i])*(x-i)


@lru_cache(None)
def draws(cohort,seed,repetitions):
    rng=random.Random(seed)
    return [tuple(rng.randrange(len(cohort)) for _ in cohort) for _ in range(repetitions)] if cohort else []


def estimate(observations,cohort,seed=20260907,repetitions=2000):
    """observations=(world,numerator,denominator), conditional ineligibility => denominator 0."""
    cohort=tuple(sorted(set(cohort))); total=defaultdict(lambda:[0.,0.])
    for world,num,den in observations:
        if world not in cohort: raise ValueError('WORLD_OUTSIDE_COHORT')
        if den<0: raise ValueError('NEGATIVE_DENOMINATOR')
        total[world][0]+=num; total[world][1]+=den
    nums=[total[w][0] for w in cohort]; dens=[total[w][1] for w in cohort]
    num=sum(nums); den=sum(dens); macro=[n/d for n,d in zip(nums,dens) if d]
    replicates=[]; macros=[]
    for draw in draws(cohort,seed,repetitions):
        dd=sum(dens[i] for i in draw)
        if dd:
            replicates.append(sum(nums[i] for i in draw)/dd)
            ww=[nums[i]/dens[i] for i in draw if dens[i]]
            macros.append(sum(ww)/len(ww))
    return dict(numerator=num,denominator=den,estimate=num/den if den else None,
        cohort_worlds=len(cohort),contributing_worlds=len(macro),world_macro=sum(macro)/len(macro) if macro else None,
        ci95_low=quantile(replicates,.025),ci95_high=quantile(replicates,.975),
        world_macro_ci95_low=quantile(macros,.025),world_macro_ci95_high=quantile(macros,.975),
        bootstrap_repetitions=repetitions,bootstrap_empty_denominator_fraction=(repetitions-len(replicates))/repetitions,
        ci_limitation='NO_DENOMINATOR' if not den else 'DEGENERATE_DESCRIPTIVE_CI_NOT_ZERO_UNCERTAINTY' if min(replicates)==max(replicates) else 'SMALL_EXPOSED_DISCOVERY_WORLD_PANEL',
        bootstrap_unit='UNDERLYING_WORLD_PAIRED_ALL_CONDITIONS',seed=seed)
