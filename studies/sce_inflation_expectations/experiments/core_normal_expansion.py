"""Consume scored LLM Core answers and expand without truth, API or Q9 fitting."""
import json
from pathlib import Path

import numpy as np

from ..core_normal_joint import JointAnswer, PointAnswer, JointExpansion
from ..monthly_analysis import weighted_summary
from ..evaluation.metrics import distribution_summary
from .frozen_batch import ROOT, dump, read_json, sha


def build_banks(population, selected, scored, *, tau):
    if scored.get('answer_origin') != 'llm_model_output' or not isinstance(scored.get('scorer_provenance'),dict):
        raise ValueError('Explicit LLM origin and frozen scorer provenance required; target truth forbidden')
    ids=[str(r['id']) for r in selected]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate selected Core')
    weights={str(r['id']):r['poststratified_weight'] for r in selected}
    q9=[];q8=[];seen=set();invalid9=[];invalid8=[]
    for r in scored['answers']:
        if set(r)-{'id','q9_bins','q9_mean','q9_iqr','q8'}:
            raise ValueError('Scored answer whitelist excludes current truth, explanations and personal records')
        uid=str(r['id'])
        if uid in seen or uid not in set(ids):raise ValueError('Only one answer per selected Core, never audit/Normal answers')
        seen.add(uid)
        point=r.get('q8')
        try:q8.append(PointAnswer(uid,point))
        except (ValueError,TypeError):point=None;invalid8.append(uid)
        try:q9.append(JointAnswer(uid,tuple(r.get('q9_bins',[])),r.get('q9_mean'),r.get('q9_iqr'),point))
        except (ValueError,TypeError):invalid9.append(uid)
    missing=sorted(set(ids)-seen)
    banks={};unsupported={}
    for name,answers in [('q9',q9),('q8',q8)]:
        try:banks[name]=JointExpansion(population,ids,answers,weights,prior_strength=tau)
        except ValueError as error:unsupported[name]=str(error)
    if not banks:raise ValueError('No independently supported Q9 or Q8 answer bank: '+str(unsupported))
    return banks, {
                'missing_core_responses':missing,'invalid_q9_core_ids':invalid9,
                'invalid_q8_core_ids':invalid8,'unsupported_banks':unsupported}


def predict(population_file, core_file, answers_file, out, *, tau, normal_seed=None):
    population_file,core_file,answers_file,out=map(lambda x:Path(x).resolve(),
                                                (population_file,core_file,answers_file,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output directory required')
    pp,cc,aa=map(read_json,(population_file,core_file,answers_file))
    if len({str(x['month']) for x in (pp,cc,aa)})!=1:raise ValueError('Month mismatch')
    banks,invalid=build_banks(pp['people'],cc['selected'],aa,tau=tau)
    first=next(iter(banks.values()));core=set(first.core_ids);normals=sorted(first.population.keys()-core)
    result={'status':'predicted_without_target_truth','month':str(pp['month']),
            'prior_strength':tau,'new_api_calls':0,'new_q9_fits':0,'failure_support':invalid,
            'scorer_provenance':aa['scorer_provenance'],'views':{},
            'source_sha256':{str(p):sha(p) for p in [population_file,core_file,answers_file,Path(__file__),
                ROOT/'studies/sce_inflation_expectations/core_normal_joint.py']}}
    atoms={}
    for name,bank in banks.items():
        atoms[name]=[{'donor_id':str(a.id),**a.payload(),'weight':float(w)}
                     for a,w in zip(bank.answers,bank.atom_weights())]
        result['views'][name]={}
        for view,targets in [('all',list(bank.population)),('normal',normals)]:
            if not targets:continue
            mass=bank.atom_weights(targets)
            if name=='q9':
                stats=distribution_summary([a.q9_mean for a in bank.answers],mass)
                stats['effective_atom_mass_size_not_person_ess']=stats.pop('ess')
                stats['valid_donor_atoms']=stats.pop('n_valid')
            else:
                stats=weighted_summary([a.q8 for a in bank.answers],mass,interpolate_median=True)
                stats['effective_atom_mass_size_not_person_ess']=stats.pop('effective_sample_size')
                stats['valid_donor_atoms']=stats.pop('n_valid')
            result['views'][name][view]={'statistics':stats,'support':bank.report(targets)}
    out.mkdir(parents=True)
    dump(out/'joint_atoms_private.json',atoms)
    if normal_seed is not None:
        visual=banks['q9'] if 'q9' in banks else banks['q8']
        dump(out/'normal_visualisation_private.json',visual.draw_normal(month=pp['month'],seed=normal_seed))
    dump(out/'summary.json',result)
    return result
