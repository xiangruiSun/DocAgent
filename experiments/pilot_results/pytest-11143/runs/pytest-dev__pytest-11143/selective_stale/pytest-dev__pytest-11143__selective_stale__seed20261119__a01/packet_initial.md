# Repository memory packet

Recorded at revision b5ff089d2cc9. The repository may have changed since.

## 1. docs/memory/src/_pytest/assertion/rewrite.part02.md

router: score=213.197, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00226] signature `_pytest.assertion.rewrite._write_pyc_fp(fp: IO[bytes], source_stat: os.stat_result, co: types.CodeType)`
- [K00227] signature `_pytest.assertion.rewrite._write_pyc(state: 'AssertionState', co: types.CodeType, source_stat: os.stat_result, pyc: Path)`
- [K00228] signature `_pytest.assertion.rewrite._rewrite_test(fn: Path, config: Config)`
- [K00229] signature `_pytest.assertion.rewrite._read_pyc(source: Path, pyc: Path, trace: Callable[[str], None]=lambda x: None)`
- [K00230] signature `_pytest.assertion.rewrite.rewrite_asserts(mod: ast.Module, source: bytes, module_path: Optional[str]=None, config: Optional[Config]=None)`
- [K00231] signature `_pytest.assertion.rewrite._saferepr(obj: object)`
- [K00232] signature `_pytest.assertion.rewrite._get_maxsize_for_saferepr(config: Optional[Config])`
- [K00233] signature `_pytest.assertion.rewrite._format_assertmsg(obj: object)`
- [K00234] signature `_pytest.assertion.rewrite._should_repr_global_name(obj: object)`
- [K00235] signature `_pytest.assertion.rewrite._format_boolop(explanations: Iterable[str], is_or: bool)`
- [K00236] signature `_pytest.assertion.rewrite._call_reprcompare(ops: Sequence[str], results: Sequence[bool], expls: Sequence[str], each_obj: Sequence[object])`
- [K00237] signature `_pytest.assertion.rewrite._call_assertion_pass(lineno: int, orig: str, expl: str)`
- [K00238] signature `_pytest.assertion.rewrite._check_if_assertion_pass_impl()`

## 2. docs/memory/src/_pytest/assertion/rewrite.part03.md

router: score=192.392, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00239] signature `_pytest.assertion.rewrite.traverse_node(node: ast.AST)`
- [K00240] signature `_pytest.assertion.rewrite._get_assertion_exprs(src: bytes)`
- [K00241] signature `_pytest.assertion.rewrite.AssertionRewriter.__init__(self, module_path: Optional[str], config: Optional[Config], source: bytes)`
- [K00242] signature `_pytest.assertion.rewrite.AssertionRewriter.run(self, mod: ast.Module)`
- [K00243] signature `_pytest.assertion.rewrite.AssertionRewriter.is_rewrite_disabled(docstring: str)`
- [K00244] signature `_pytest.assertion.rewrite.AssertionRewriter.variable(self)`
- [K00245] signature `_pytest.assertion.rewrite.AssertionRewriter.assign(self, expr: ast.expr)`
- [K00246] signature `_pytest.assertion.rewrite.AssertionRewriter.display(self, expr: ast.expr)`
- [K00247] signature `_pytest.assertion.rewrite.AssertionRewriter.helper(self, name: str, *args: ast.expr)`
- [K00248] signature `_pytest.assertion.rewrite.AssertionRewriter.builtin(self, name: str)`
- [K00249] signature `_pytest.assertion.rewrite.AssertionRewriter.explanation_param(self, expr: ast.expr)`
- [K00250] signature `_pytest.assertion.rewrite.AssertionRewriter.push_format_context(self)`
- [K00251] signature `_pytest.assertion.rewrite.AssertionRewriter.pop_format_context(self, expl_expr: ast.expr)`
- [K00252] signature `_pytest.assertion.rewrite.AssertionRewriter.generic_visit(self, node: ast.AST)`

## 3. docs/memory/src/_pytest/assertion/rewrite.part01.md

router: score=182.598, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00215] signature `_pytest.assertion.rewrite.AssertionRewritingHook.__init__(self, config: Config)`
- [K00216] signature `_pytest.assertion.rewrite.AssertionRewritingHook.set_session(self, session: Optional[Session])`
- [K00217] signature `_pytest.assertion.rewrite.AssertionRewritingHook.find_spec(self, name: str, path: Optional[Sequence[Union[str, bytes]]]=None, target: Optional[types.ModuleType]=None)`
- [K00218] signature `_pytest.assertion.rewrite.AssertionRewritingHook.create_module(self, spec: importlib.machinery.ModuleSpec)`
- [K00219] signature `_pytest.assertion.rewrite.AssertionRewritingHook.exec_module(self, module: types.ModuleType)`
- [K00220] signature `_pytest.assertion.rewrite.AssertionRewritingHook._early_rewrite_bailout(self, name: str, state: 'AssertionState')`
- [K00221] signature `_pytest.assertion.rewrite.AssertionRewritingHook._should_rewrite(self, name: str, fn: str, state: 'AssertionState')`
- [K00222] signature `_pytest.assertion.rewrite.AssertionRewritingHook._is_marked_for_rewrite(self, name: str, state: 'AssertionState')`
- [K00223] signature `_pytest.assertion.rewrite.AssertionRewritingHook.mark_rewrite(self, *names: str)`
- [K00224] signature `_pytest.assertion.rewrite.AssertionRewritingHook._warn_already_imported(self, name: str)`
- [K00225] signature `_pytest.assertion.rewrite.AssertionRewritingHook.get_data(self, pathname: Union[str, bytes])`

## 4. docs/memory/src/_pytest/assertion/rewrite.part04.md

router: score=170.541, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00253] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Assert(self, assert_: ast.Assert)`
- [K00254] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_NamedExpr(self, name: namedExpr)`
- [K00255] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Name(self, name: ast.Name)`
- [K00256] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_BoolOp(self, boolop: ast.BoolOp)`
- [K00257] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_UnaryOp(self, unary: ast.UnaryOp)`
- [K00258] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_BinOp(self, binop: ast.BinOp)`
- [K00259] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Call(self, call: ast.Call)`
- [K00260] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Starred(self, starred: ast.Starred)`
- [K00261] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Attribute(self, attr: ast.Attribute)`
- [K00262] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Compare(self, comp: ast.Compare)`
- [K00263] signature `_pytest.assertion.rewrite.try_makedirs(cache_dir: Path)`
- [K00264] signature `_pytest.assertion.rewrite.get_cache_dir(file_path: Path)`

## 5. docs/memory/src/_pytest/runner.part02.md

router: score=168.0, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/runner.py)
source: `src/_pytest/runner.py`

- [K01352] signature `_pytest.runner.CallInfo.__init__(self, result: Optional[TResult], excinfo: Optional[ExceptionInfo[BaseException]], start: float, stop: float, duration: float, when: "Literal['collect', 'setup', 'call', 'teardown']", *, _ispytest: bool=False)`
- [K01353] signature `_pytest.runner.CallInfo.result(self)`
- [K01354] signature `_pytest.runner.CallInfo.from_call(cls, func: 'Callable[[], TResult]', when: "Literal['collect', 'setup', 'call', 'teardown']", reraise: Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]]=None)`
- [K01355] signature `_pytest.runner.pytest_runtest_makereport(item: Item, call: CallInfo[None])`
- [K01356] signature `_pytest.runner.pytest_make_collect_report(collector: Collector)`
- [K01357] signature `_pytest.runner.SetupState.__init__(self)`
- [K01358] signature `_pytest.runner.SetupState.setup(self, item: Item)`
- [K01359] signature `_pytest.runner.SetupState.addfinalizer(self, finalizer: Callable[[], object], node: Node)`
- [K01360] signature `_pytest.runner.SetupState.teardown_exact(self, nextitem: Optional[Item])`
- [K01361] signature `_pytest.runner.collect_one_node(collector: Collector)`
