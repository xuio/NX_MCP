import sys
from copy import deepcopy
from types import ModuleType, SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import heat_edit as mod


@pytest.fixture
def rig(monkeypatch):
    nx = ModuleType('NXOpen')
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    nx.Update = NS(Option=NS(Now=1))
    monkeypatch.setitem(sys.modules, 'NXOpen', nx)
    state = dict(power_w=22., wrapper=10, expression=11, provenance='old', invariants={'target': 3})
    ref = {'journal_id': 'load', 'owner_path': 'sim'}
    inv = dict(objects=[9], loads=[1,2], constraints=[4], expressions=[11], fields=[], modified=False,
               solution_bcs=[1,2], membership={'comparison_verified': True, 'solution': {'bcs': [ref]}, 'steps': [{'bcs': []}]},
               heat={'1': deepcopy(state), '2': {'power_w': 8., 'wrapper': 10}})
    original, oldinv = deepcopy(state), deepcopy(inv)
    writes = []
    def bind(_, value):
        writes.append(value)
        state.update(power_w=value, wrapper=12, expression=13)
        inv['expressions'].append(13)
        inv['modified'] = True
    load = NS(Tag=1, JournalIdentifier='load', PropertyTable=NS(SetScalarFieldWrapperPropertyValue=bind),
              SetUserAttribute=lambda _a,_i,value,_u: state.update(provenance=value))
    sol = NS(SolverType='NX MULTIPHYSICS', AnalysisType='Thermal', StepCount=1)
    sim = NS(FullPath='sim', Simulation=NS(ActiveSolution=sol, Solutions=[sol]),
             Expressions=NS(CreateSystemNumberExpression=lambda value,_: float(value)),
             FieldManager=NS(CreateScalarFieldWrapperWithExpression=lambda e:e), UnitCollection=NS(FindObject=lambda _: 'W'))
    def inspect(*_): return deepcopy(state)
    def inventory(*_):
        result = deepcopy(inv); result['heat']['1'] = deepcopy(state); return result
    def undo(*_):
        state.clear(); state.update(deepcopy(original)); inv.clear(); inv.update(deepcopy(oldinv))
    session = NS(Parts=NS(BaseWork=sim), SetUndoMark=lambda *_: 1, UndoToMark=undo,
                 DeleteUndoMark=lambda *_: None, UpdateManager=NS(DoUpdate=lambda _:0))
    monkeypatch.setattr(mod,'inspect',inspect)
    monkeypatch.setattr(mod,'inventory',inventory)
    return session,sim,load,state,inv,writes


def test_change_preserves_other_shared_binding_and_noop(rig):
    session,sim,load,state,inv,writes=rig
    result=mod.edit(session,sim,load,22.,14.165,'new')
    assert result['all_heat_loads_total_w']==22.165
    assert inv['heat']['2']=={'power_w':8.,'wrapper':10}
    assert state['wrapper']==12 and state['provenance']=='new'
    assert not mod.edit(session,sim,load,14.165,14.165,'new')['changed']
    assert len(writes)==1


@pytest.mark.parametrize('value',[True,-1,float('nan'),float('inf'),'14'])
def test_invalid_heat_is_not_written(rig,value):
    with pytest.raises(NXToolError): mod.edit(*rig[:3],22,value,'new')
    assert not rig[5]


def test_stale_expected_value_is_not_written(rig):
    with pytest.raises(NXToolError,match='Existing power'): mod.edit(*rig[:3],21,14,'new')
    assert not rig[5]


@pytest.mark.parametrize('failure',['update','target','other_load','membership','provenance','rollback'])
def test_failed_edit_restores_or_reports_partial(rig,failure):
    session,sim,load,state,inv,writes=rig
    def update(_):
        if failure in ('update','rollback'): return 1
        if failure=='target': state['invariants']['target']=99
        if failure=='other_load': inv['heat']['2']['power_w']=99
        if failure=='membership': inv['solution_bcs']=[]
        if failure=='provenance': state['provenance']='wrong'
        return 0
    session.UpdateManager.DoUpdate=update
    if failure=='rollback': session.UndoToMark=lambda *_:None
    with pytest.raises(NXToolError) as exc: mod.edit(session,sim,load,22,14,'new')
    assert exc.value.details['mutation_outcome']==('partial' if failure=='rollback' else 'rolled_back')
    if failure!='rollback': assert state['power_w']==22 and state['provenance']=='old'


@pytest.mark.parametrize('failure',['folder','step','not_member','two_solutions','flow'])
def test_unsupported_membership_or_solution_never_mutates(rig,failure):
    session,sim,load,state,inv,writes=rig
    if failure=='folder': inv['membership']['comparison_verified']=False
    if failure=='step': inv['membership']['steps'][0]['bcs']=inv['membership']['solution']['bcs'][:]
    if failure=='not_member': inv['membership']['solution']['bcs']=[]
    if failure=='two_solutions': sim.Simulation.Solutions.append(NS())
    if failure=='flow': sim.Simulation.ActiveSolution.AnalysisType='Flow'
    with pytest.raises(NXToolError): mod.edit(session,sim,load,22,14,'new')
    assert not writes


def test_busy_solver_blocks_before_resolution(monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin
    nx,cae=ModuleType('NXOpen'),ModuleType('NXOpen.CAE'); nx.CAE=cae
    monkeypatch.setitem(sys.modules,'NXOpen',nx);monkeypatch.setitem(sys.modules,'NXOpen.CAE',cae)
    def busy(): raise NXToolError('NX_SIM_SOLVER_BUSY','busy')
    monkeypatch.setattr(solver_guard,'require_solver_idle',busy)
    with pytest.raises(NXToolError) as exc: SimcenterMixin._sim_edit_heat_power(NS(),'doc','load',22,14,'new')
    assert exc.value.code=='NX_SIM_SOLVER_BUSY'


@pytest.mark.parametrize('bad',[None,'owner','descriptor','accounting','controller','field','units','formula','negative','target','unreadable'])
def test_inspect_binding_guards(monkeypatch,bad):
    from nx_mcp.simcenter import properties
    nx,cae=ModuleType('NXOpen'),ModuleType('NXOpen.CAE'); nx.CAE=cae
    class Body: pass
    cae.CAEBody=Body
    monkeypatch.setitem(sys.modules,'NXOpen',nx);monkeypatch.setitem(sys.modules,'NXOpen.CAE',cae)
    sim=NS()
    body=Body();body.Tag=3;body.OwningPart=sim
    expression=NS(Tag=11,GetFormula=lambda:'22.0',Units=NS(Symbol='W'))
    wrapper=NS(Tag=10,GetExpression=lambda:expression,GetField=lambda:None)
    values={'Selection Method':0,'Override Region':False,'Specify Reference Temperature Set':False,
            'Control Heater':False,'Specify Layer to Apply to':False,'Apply to':0,'Layer Number':1,
            'Per Element':False,'Per Node':False,'distributionType':32,'Custom Settings Option':False}
    props=[{'name':k,'value':v} for k,v in values.items()]+[{'name':'Heat Load Override','expression':'-777777'}]
    attrs={'NX_MCP_ENERGY_ACCOUNTING':'internal_heat','NX_MCP_PROVENANCE':'old','NX_MCP_HEAT_OVERLAP_POLICY':'reject'}
    member=NS(Obj=body,SubId=0,SubType=0)
    load=NS(OwningPart=sim,DescriptorName='Heat Load',Name='heat',
            GetStringUserAttribute=lambda k,_:attrs[k],PropertyTable=NS(GetScalarFieldWrapperPropertyValue=lambda _:wrapper),
            TargetSetManager=NS(TargetSetCount=2,GetTargetSetMembers=lambda i:(0,[member] if i==0 else [None])))
    monkeypatch.setattr(properties,'read_properties',lambda *_:props)
    if bad=='owner':load.OwningPart=None
    if bad=='descriptor':load.DescriptorName='Other'
    if bad=='accounting':attrs['NX_MCP_ENERGY_ACCOUNTING']='exported'
    if bad=='controller':next(p for p in props if p['name']=='Control Heater')['value']=True
    if bad=='field':wrapper.GetField=lambda:object()
    if bad=='units':expression.Units.Symbol='kW'
    if bad=='formula':expression.GetFormula=lambda:'p1+1'
    if bad=='negative':expression.GetFormula=lambda:'-1'
    if bad=='target':member.SubId=2
    if bad=='unreadable':props.append({'inspection_status':'unsupported'})
    if bad is None:
        assert mod.inspect(sim,load)['power_w']==22
    else:
        with pytest.raises(NXToolError):mod.inspect(sim,load)
