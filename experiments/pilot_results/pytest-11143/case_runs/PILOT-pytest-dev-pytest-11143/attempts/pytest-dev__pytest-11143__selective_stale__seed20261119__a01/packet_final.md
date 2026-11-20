# Repository memory packet

Recorded at revision b5ff089d2cc9. The repository may have changed since.

## 1. docs/memory/src/_pytest/assertion/rewrite.part02.md

router: score=213.197, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00226] signature `_pytest.assertion.rewrite._write_pyc_fp(fp: IO[bytes], source_stat: os.stat_result, co: types.CodeType)`  [checked: supported]
- [K00227] signature `_pytest.assertion.rewrite._write_pyc(state: 'AssertionState', co: types.CodeType, source_stat: os.stat_result, pyc: Path)`  [checked: supported]
- [K00228] signature `_pytest.assertion.rewrite._rewrite_test(fn: Path, config: Config)`  [checked: supported]
- [K00229] signature `_pytest.assertion.rewrite._read_pyc(source: Path, pyc: Path, trace: Callable[[str], None]=lambda x: None)`  [unchecked]
- [K00230] signature `_pytest.assertion.rewrite.rewrite_asserts(mod: ast.Module, source: bytes, module_path: Optional[str]=None, config: Optional[Config]=None)`  [unchecked]
- [K00231] signature `_pytest.assertion.rewrite._saferepr(obj: object)`  [unchecked]
- [K00232] signature `_pytest.assertion.rewrite._get_maxsize_for_saferepr(config: Optional[Config])`  [unchecked]
- [K00233] signature `_pytest.assertion.rewrite._format_assertmsg(obj: object)`  [unchecked]
- [K00234] signature `_pytest.assertion.rewrite._should_repr_global_name(obj: object)`  [unchecked]
- [K00235] signature `_pytest.assertion.rewrite._format_boolop(explanations: Iterable[str], is_or: bool)`  [unchecked]
- [K00236] signature `_pytest.assertion.rewrite._call_reprcompare(ops: Sequence[str], results: Sequence[bool], expls: Sequence[str], each_obj: Sequence[object])`  [unchecked]
- [K00237] signature `_pytest.assertion.rewrite._call_assertion_pass(lineno: int, orig: str, expl: str)`  [unchecked]
- [K00238] signature `_pytest.assertion.rewrite._check_if_assertion_pass_impl()`  [unchecked]

## 2. docs/memory/src/_pytest/assertion/rewrite.part03.md

router: score=192.392, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00239] signature `_pytest.assertion.rewrite.traverse_node(node: ast.AST)`  [unchecked]
- [K00240] signature `_pytest.assertion.rewrite._get_assertion_exprs(src: bytes)`  [unchecked]
- [K00241] signature `_pytest.assertion.rewrite.AssertionRewriter.__init__(self, module_path: Optional[str], config: Optional[Config], source: bytes)`  [unchecked]
- [K00242] signature `_pytest.assertion.rewrite.AssertionRewriter.run(self, mod: ast.Module)`  [unchecked]
- [K00243] signature `_pytest.assertion.rewrite.AssertionRewriter.is_rewrite_disabled(docstring: str)`  [unchecked]
- [K00244] signature `_pytest.assertion.rewrite.AssertionRewriter.variable(self)`  [unchecked]
- [K00245] signature `_pytest.assertion.rewrite.AssertionRewriter.assign(self, expr: ast.expr)`  [unchecked]
- [K00246] signature `_pytest.assertion.rewrite.AssertionRewriter.display(self, expr: ast.expr)`  [unchecked]
- [K00247] signature `_pytest.assertion.rewrite.AssertionRewriter.helper(self, name: str, *args: ast.expr)`  [unchecked]
- [K00248] signature `_pytest.assertion.rewrite.AssertionRewriter.builtin(self, name: str)`  [unchecked]
- [K00249] signature `_pytest.assertion.rewrite.AssertionRewriter.explanation_param(self, expr: ast.expr)`  [unchecked]
- [K00250] signature `_pytest.assertion.rewrite.AssertionRewriter.push_format_context(self)`  [unchecked]
- [K00251] signature `_pytest.assertion.rewrite.AssertionRewriter.pop_format_context(self, expl_expr: ast.expr)`  [unchecked]
- [K00252] signature `_pytest.assertion.rewrite.AssertionRewriter.generic_visit(self, node: ast.AST)`  [unchecked]

## 3. docs/memory/src/_pytest/assertion/rewrite.part01.md

router: score=182.598, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00215] signature `_pytest.assertion.rewrite.AssertionRewritingHook.__init__(self, config: Config)`  [unchecked]
- [K00216] signature `_pytest.assertion.rewrite.AssertionRewritingHook.set_session(self, session: Optional[Session])`  [unchecked]
- [K00217] signature `_pytest.assertion.rewrite.AssertionRewritingHook.find_spec(self, name: str, path: Optional[Sequence[Union[str, bytes]]]=None, target: Optional[types.ModuleType]=None)`  [unchecked]
- [K00218] signature `_pytest.assertion.rewrite.AssertionRewritingHook.create_module(self, spec: importlib.machinery.ModuleSpec)`  [unchecked]
- [K00219] signature `_pytest.assertion.rewrite.AssertionRewritingHook.exec_module(self, module: types.ModuleType)`  [unchecked]
- [K00220] signature `_pytest.assertion.rewrite.AssertionRewritingHook._early_rewrite_bailout(self, name: str, state: 'AssertionState')`  [unchecked]
- [K00221] signature `_pytest.assertion.rewrite.AssertionRewritingHook._should_rewrite(self, name: str, fn: str, state: 'AssertionState')`  [unchecked]
- [K00222] signature `_pytest.assertion.rewrite.AssertionRewritingHook._is_marked_for_rewrite(self, name: str, state: 'AssertionState')`  [unchecked]
- [K00223] signature `_pytest.assertion.rewrite.AssertionRewritingHook.mark_rewrite(self, *names: str)`  [unchecked]
- [K00224] signature `_pytest.assertion.rewrite.AssertionRewritingHook._warn_already_imported(self, name: str)`  [unchecked]
- [K00225] signature `_pytest.assertion.rewrite.AssertionRewritingHook.get_data(self, pathname: Union[str, bytes])`  [unchecked]

## 4. docs/memory/src/_pytest/assertion/rewrite.part04.md

router: score=170.541, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/assertion/rewrite.py)
source: `src/_pytest/assertion/rewrite.py`

- [K00253] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Assert(self, assert_: ast.Assert)`  [unchecked]
- [K00254] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_NamedExpr(self, name: namedExpr)`  [unchecked]
- [K00255] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Name(self, name: ast.Name)`  [unchecked]
- [K00256] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_BoolOp(self, boolop: ast.BoolOp)`  [unchecked]
- [K00257] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_UnaryOp(self, unary: ast.UnaryOp)`  [unchecked]
- [K00258] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_BinOp(self, binop: ast.BinOp)`  [unchecked]
- [K00259] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Call(self, call: ast.Call)`  [unchecked]
- [K00260] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Starred(self, starred: ast.Starred)`  [unchecked]
- [K00261] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Attribute(self, attr: ast.Attribute)`  [unchecked]
- [K00262] signature `_pytest.assertion.rewrite.AssertionRewriter.visit_Compare(self, comp: ast.Compare)`  [unchecked]
- [K00263] signature `_pytest.assertion.rewrite.try_makedirs(cache_dir: Path)`  [unchecked]
- [K00264] signature `_pytest.assertion.rewrite.get_cache_dir(file_path: Path)`  [unchecked]

## 5. docs/memory/src/_pytest/runner.part02.md

router: score=168.0, authority=current-state, freshness=stale-document (covered file changed: src/_pytest/runner.py)
source: `src/_pytest/runner.py`

- [K01352] signature `_pytest.runner.CallInfo.__init__(self, result: Optional[TResult], excinfo: Optional[ExceptionInfo[BaseException]], start: float, stop: float, duration: float, when: "Literal['collect', 'setup', 'call', 'teardown']", *, _ispytest: bool=False)`  [unchecked]
- [K01353] signature `_pytest.runner.CallInfo.result(self)`  [unchecked]
- [K01354] signature `_pytest.runner.CallInfo.from_call(cls, func: 'Callable[[], TResult]', when: "Literal['collect', 'setup', 'call', 'teardown']", reraise: Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]]=None)`  [unchecked]
- [K01355] signature `_pytest.runner.pytest_runtest_makereport(item: Item, call: CallInfo[None])`  [unchecked]
- [K01356] signature `_pytest.runner.pytest_make_collect_report(collector: Collector)`  [unchecked]
- [K01357] signature `_pytest.runner.SetupState.__init__(self)`  [unchecked]
- [K01358] signature `_pytest.runner.SetupState.setup(self, item: Item)`  [unchecked]
- [K01359] signature `_pytest.runner.SetupState.addfinalizer(self, finalizer: Callable[[], object], node: Node)`  [unchecked]
- [K01360] signature `_pytest.runner.SetupState.teardown_exact(self, nextitem: Optional[Item])`  [unchecked]
- [K01361] signature `_pytest.runner.collect_one_node(collector: Collector)`  [unchecked]

Check legend: [checked: supported] was confirmed in the current source; [repaired] was rewritten from the current source; [omitted] could not be confirmed; [unchecked] and unmarked claims were not checked.
