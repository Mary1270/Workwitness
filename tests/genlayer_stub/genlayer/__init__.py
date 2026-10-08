import copy
import re
import types

__all__ = ["gl", "Address", "u256", "TreeMap", "DynArray", "allow_storage"]


class UserError(Exception):
    pass


class ConsensusFailure(Exception):
    pass


class Address:
    def __init__(self, value):
        if isinstance(value, Address):
            value = value._s
        if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
            raise ValueError("invalid address")
        self._s = "0x" + value[2:].lower()

    def __str__(self):
        return self._s

    def __eq__(self, other):
        return isinstance(other, Address) and other._s == self._s

    def __hash__(self):
        return hash(self._s)


def u256(value):
    value = int(value)
    if value < 0 or value >= 2**256:
        raise OverflowError("u256 out of range")
    return value


class TreeMap(dict):
    def __class_getitem__(cls, item):
        return cls

    def get(self, *args, **kwargs):
        raise AttributeError("TreeMap.get is not supported on GenVM storage; use 'in' and []")


class DynArray(list):
    def __class_getitem__(cls, item):
        return cls


def allow_storage(cls):
    return cls


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class Frame:
    def __init__(self, contract, sender, value):
        self.contract = contract
        self.sender = sender
        self.value = value


class Runtime:
    def __init__(self):
        self.reset()

    def reset(self):
        self.contracts = {}
        self.balances = {}
        self.stack = []
        self.pages = {}
        self.llm = None
        self.in_nondet = False
        self.n_validators = 5
        self.envs = {}
        self.active = 0
        self.tamper = None
        self.failed = []
        self.fetch_log = []
        self.next_addr = 1
        self.drop = set()
        self.dropped = []
        self.emitted = []

    def frame(self):
        if not self.stack:
            raise RuntimeError("no active frame")
        return self.stack[-1]

    def snapshot(self):
        return (
            {addr: copy.deepcopy(inst.__dict__) for addr, inst in self.contracts.items()},
            dict(self.balances),
        )

    def restore(self, snap):
        states, balances = snap
        for addr, state in states.items():
            self.contracts[addr].__dict__.clear()
            self.contracts[addr].__dict__.update(state)
        self.balances = dict(balances)

    def deploy(self, cls, args, sender):
        addr = "0x" + format(0xC0DE00000000 + self.next_addr, "040x")
        self.next_addr += 1
        inst = cls.__new__(cls)
        for klass in reversed(cls.__mro__):
            for name, ann in getattr(klass, "__annotations__", {}).items():
                object.__setattr__(inst, name, _zero(ann))
        self.contracts[addr] = inst
        self.balances[addr] = 0
        self.stack.append(Frame(addr, sender, 0))
        try:
            inst.__init__(*args)
        except Exception:
            del self.contracts[addr]
            raise
        finally:
            self.stack.pop()
        return addr

    def invoke(self, to, method, args, sender, value=0, mode="write"):
        if self.in_nondet:
            raise RuntimeError("contract calls are not allowed inside a non-deterministic block")
        inst = self.contracts[to]
        fn = getattr(type(inst), method, None)
        kind = getattr(fn, "_gl_kind", None)
        if kind is None:
            raise UserError("method is not public")
        if mode == "view" and kind != "view":
            raise UserError("write method called as view")
        if mode != "view" and kind == "view":
            raise UserError("view method called as write")
        if value and kind != "payable":
            raise UserError("method is not payable")
        if value:
            self.balances[to] = self.balances.get(to, 0) + value
        self.stack.append(Frame(to, sender, value))
        try:
            return fn(inst, *args)
        finally:
            self.stack.pop()

    def emit_call(self, to, method, args, value, on=None):
        self.emitted.append((method, on))
        if method in self.drop:
            self.dropped.append(method)
            return
        sender = self.frame().contract
        inst = self.contracts[to]
        snap_state = copy.deepcopy(inst.__dict__)
        snap_bal = dict(self.balances)
        saved_stack = list(self.stack)
        try:
            self.invoke(to, method, args, sender, value, "write")
        except Exception as exc:
            self.stack = saved_stack
            inst.__dict__.clear()
            inst.__dict__.update(snap_state)
            self.balances = snap_bal
            self.failed.append((to, method, str(exc)))

    def transfer(self, to, value):
        if self.in_nondet:
            raise RuntimeError("transfers are not allowed inside a non-deterministic block")
        src = self.frame().contract
        if self.balances.get(src, 0) < value:
            raise UserError("contract balance too low")
        self.balances[src] -= value
        self.balances[to] = self.balances.get(to, 0) + value

    def env(self):
        return self.envs.get(self.active, {})


RT = Runtime()


def _zero(ann):
    if isinstance(ann, type) and issubclass(ann, TreeMap):
        return TreeMap()
    if isinstance(ann, type) and issubclass(ann, DynArray):
        return DynArray()
    if ann is u256 or ann is int:
        return 0
    if ann is str:
        return ""
    if ann is bool:
        return False
    return None


class Contract:
    def __setattr__(self, name, value):
        ann = None
        for klass in type(self).__mro__:
            if name in getattr(klass, "__annotations__", {}):
                ann = klass.__annotations__[name]
                break
        if isinstance(ann, type) and issubclass(ann, TreeMap) and not isinstance(value, TreeMap):
            raise AssertionError("Is right the same storage type? TreeMap <- " + type(value).__name__)
        if isinstance(ann, type) and issubclass(ann, DynArray) and not isinstance(value, DynArray):
            value = DynArray(value)
        object.__setattr__(self, name, value)


class _Writer:
    def __call__(self, fn):
        fn._gl_kind = "write"
        return fn

    def payable(self, fn):
        fn._gl_kind = "payable"
        return fn


class _Public:
    @staticmethod
    def view(fn):
        fn._gl_kind = "view"
        return fn

    write = _Writer()


class _Message:
    @property
    def sender_address(self):
        return Address(RT.frame().sender)

    @property
    def value(self):
        return RT.frame().value


class _Caller:
    def __init__(self, addr, mode, value=0, on=None):
        self._addr = addr
        self._mode = mode
        self._value = value
        self._on = on

    def __getattr__(self, method):
        def call(*args):
            if self._mode == "emit":
                return RT.emit_call(self._addr, method, args, self._value, self._on)
            return RT.invoke(self._addr, method, args, RT.frame().contract, 0, "view")

        return call


class _ContractAt:
    def __init__(self, addr):
        if not isinstance(addr, Address):
            raise TypeError("get_contract_at expects an Address")
        self._addr = str(addr)

    def view(self):
        return _Caller(self._addr, "view")

    def emit(self, on=None, value=0):
        if on not in ("accepted", "finalized"):
            raise ValueError("emit requires on='accepted' or on='finalized'")
        return _Caller(self._addr, "emit", int(value), on)

    def emit_transfer(self, value=0, **kwargs):
        if kwargs:
            raise SystemError("emit_transfer to a plain wallet takes only value=")
        RT.transfer(self._addr, int(value))


def _get_contract_at(addr):
    return _ContractAt(addr)


def _run_nondet_unsafe(leader_fn, validator_fn):
    if RT.in_nondet:
        raise RuntimeError("nested non-deterministic block")
    RT.in_nondet = True
    try:
        RT.active = 0
        leader_res = leader_fn()
        if RT.tamper is not None:
            leader_res = RT.tamper(leader_res)
        agree = 1
        for index in range(1, RT.n_validators):
            RT.active = index
            try:
                ok = validator_fn(Return(leader_res))
            except Exception:
                ok = False
            if ok:
                agree += 1
    finally:
        RT.active = 0
        RT.in_nondet = False
    if agree * 2 <= RT.n_validators:
        raise ConsensusFailure("validators did not reach agreement")
    return leader_res


def _render(url, mode="text"):
    if not RT.in_nondet:
        raise RuntimeError("web access outside a non-deterministic block")
    RT.fetch_log.append((RT.active, url))
    pages = RT.env().get("pages", RT.pages)
    if url not in pages:
        raise Exception("WEBPAGE_LOAD_FAILED")
    page = pages[url]
    if isinstance(page, Exception):
        raise page
    return page


def _exec_prompt(prompt, response_format="text", **kwargs):
    if not RT.in_nondet:
        raise RuntimeError("LLM access outside a non-deterministic block")
    llm = RT.env().get("llm", RT.llm)
    return llm(prompt)


gl = types.SimpleNamespace(
    Contract=Contract,
    public=_Public,
    message=_Message(),
    get_contract_at=_get_contract_at,
    vm=types.SimpleNamespace(UserError=UserError, Return=Return, run_nondet_unsafe=_run_nondet_unsafe),
    nondet=types.SimpleNamespace(web=types.SimpleNamespace(render=_render), exec_prompt=_exec_prompt),
)
