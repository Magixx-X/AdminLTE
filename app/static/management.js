(function ($) {
  'use strict';
  window.managementPage = function (page, api, message, esc) {
    var items = [], departments = [], roles = [], menuOptions = [], selectedDepartment = '', editing = null;
    var collapsed = new Set(), hiddenColumns = new Set(), filters = {name:'', contact:'', status:''};
    var key = {users:'user', roles:'role', menus:'menu', departments:'department', connections:'connection'}[page];
    var entity = {users:'用户', roles:'角色', menus:'菜单', departments:'部门', connections:'连接'}[page];
    var fields = {
      users:[['id','编号'],['username','名称'],['nickname','昵称'],['department','部门'],['contact','联系方式'],['enabled','状态'],['created_at','创建时间']],
      roles:[['id','编号'],['name','角色名称'],['code','角色标识'],['enabled','状态'],['created_at','创建时间'],['remark','备注']],
      departments:[['name','部门名称'],['code','部门代码'],['position','排序'],['enabled','状态'],['created_at','创建时间'],['remark','备注']],
      menus:[['title','菜单名称'],['kind','菜单类型'],['path','路由路径'],['permission','权限标识'],['position','排序'],['enabled','状态']],
      connections:[['id','编号'],['name','连接名称'],['engine','数据库'],['mode','连接方式'],['namespace','命名空间'],['address','地址 / 实例'],['username','用户名'],['enabled','状态'],['last_test_status','测试结果'],['last_test_at','测试时间']]
    };
    var treePage = page === 'menus' || page === 'departments';
    function action(label, cls, id) {
      return '<button type="button" class="btn btn-link btn-sm ' + cls + '" data-id="' + esc(id) + '">' + label + '</button>';
    }
    function timeLabel(value) {
      if (!value) { return '—'; }
      var date = new Date(value);
      return isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {hour12:false});
    }
    function byCode(values, code) { return values.find(function (item) { return item.code === code; }); }
    function descendantCodes(values, code) {
      var result = new Set([code]);
      function visit(parent) { values.forEach(function (item) { if (item.parent === parent && !result.has(item.code)) { result.add(item.code); visit(item.code); } }); }
      visit(code); return result;
    }
    function ordered(values, comparator) {
      var result = [], visited = new Set();
      function visit(parent, depth) {
        values.filter(function (item) { return (item.parent || null) === parent; }).sort(comparator).forEach(function (item) {
          if (visited.has(item.code)) { return; }
          visited.add(item.code); result.push({item:item, depth:depth}); visit(item.code, depth + 1);
        });
      }
      visit(null, 0); return result;
    }
    function departmentNames(user) {
      return (user.scopes || []).map(function (code) { var dept = byCode(departments, code); return dept ? dept.name : code; }).join('、') || '—';
    }
    function value(item, field) { return field === 'department' ? departmentNames(item) : item[field]; }
    function comparator(a, b) {
      var field = $('#sort-field').val(), av = value(a, field), bv = value(b, field);
      var result = typeof av === 'number' || typeof av === 'boolean' ? Number(av) - Number(bv) : String(av || '').localeCompare(String(bv || ''), 'zh-CN', {numeric:true});
      return ($('#sort-direction').val() === 'desc' ? -result : result) || String(a.code || a.id).localeCompare(String(b.code || b.id));
    }
    function render() {
      var visibleFields = fields[page].filter(function (field) { return !hiddenColumns.has(field[0]); });
      var departmentSet = selectedDepartment ? descendantCodes(departments, selectedDepartment) : null;
      var matching = items.filter(function (item) {
        var name = page === 'users' ? item.username + ' ' + item.nickname : (item.name || item.title) + ' ' + (item.code || '');
        return name.toLowerCase().includes(filters.name.toLowerCase()) &&
          (!filters.contact || String(item.contact || '').includes(filters.contact)) &&
          (!filters.status || String(item.enabled) === filters.status) && (!filters.engine || item.engine === filters.engine) &&
          (!departmentSet || (item.scopes || []).some(function (code) { return departmentSet.has(code); }));
      });
      var searching = filters.name || filters.status;
      var visibleCodes = new Set(matching.map(function (item) { return item.code; }));
      if (treePage && searching) {
        matching.forEach(function (item) { var parent = item.parent; while (parent && !visibleCodes.has(parent)) { visibleCodes.add(parent); var row = byCode(items, parent); parent = row ? row.parent : null; } });
      }
      var rows = treePage ? ordered(items, comparator).filter(function (row) {
        if (searching) { return visibleCodes.has(row.item.code); }
        var parent = row.item.parent;
        while (parent) { if (collapsed.has(parent)) { return false; } var ancestor = byCode(items, parent); parent = ancestor ? ancestor.parent : null; }
        return true;
      }) : matching.sort(comparator).map(function (item) { return {item:item, depth:0}; });
      var html = '<table class="table management-grid"><thead><tr>';
      visibleFields.forEach(function (field) {
        var sorted = $('#sort-field').val() === field[0];
        html += '<th scope="col"' + (sorted ? ' aria-sort="' + ($('#sort-direction').val() === 'asc' ? 'ascending' : 'descending') + '"' : '') + '><button type="button" class="sort-heading" data-field="' + field[0] + '">' + field[1] + (sorted ? ' <i class="fas fa-sort-' + ($('#sort-direction').val() === 'asc' ? 'up' : 'down') + '" aria-hidden="true"></i>' : '') + '</button></th>';
      });
      html += '<th scope="col" class="actions-column">操作</th></tr></thead><tbody>';
      rows.forEach(function (row) {
        var item = row.item, id = treePage ? item.code : item.id;
        html += '<tr>';
        visibleFields.forEach(function (field, index) {
          var val = value(item, field[0]), cell = esc(val || (val === 0 ? 0 : '—'));
          if (field[0] === 'enabled') { cell = '<span class="status-tag ' + (val ? 'status-enabled' : 'status-disabled') + '">' + (val ? '启用' : '停用') + '</span>'; }
          if (field[0] === 'created_at') { cell = esc(timeLabel(val)); }
          if (field[0] === 'last_test_at') { cell = esc(timeLabel(val)); }
          if (field[0] === 'engine') { cell = {oracle:'Oracle', mysql:'MySQL', sqlserver:'SQL Server'}[val]; }
          if (field[0] === 'mode') { cell = val === 'tcp' ? 'IP + 端口' : '本地实例'; }
          if (field[0] === 'last_test_status') { cell = '<span class="status-tag ' + (val === 'PASSED' ? 'status-enabled' : val === 'FAILED' ? 'status-disabled' : 'status-pending') + '">' + ({PASSED:'已通过', FAILED:'未通过', UNTESTED:'未测试'}[val] || '未测试') + '</span>' + (item.is_query_source ? ' <span class="status-tag status-pending">查询数据源</span>' : ''); }
          if (treePage && index === 0) {
            var children = items.some(function (child) { return child.parent === id; });
            cell = '<span class="tree-cell" style="padding-left:' + row.depth * 20 + 'px">' + (children ? '<button type="button" class="tree-toggle" data-id="' + esc(id) + '" aria-label="展开或收起' + entity + '" aria-expanded="' + (searching || !collapsed.has(id)) + '"><i class="fas fa-chevron-' + (collapsed.has(id) && !searching ? 'right' : 'down') + '" aria-hidden="true"></i></button>' : '<span class="tree-spacer"></span>') + cell + '</span>';
          }
          html += '<td' + (field[0] === 'remark' || field[0] === 'permission' ? ' class="description-cell"' : '') + '>' + cell + '</td>';
        });
        html += '<td class="row-actions">' + action('编辑', 'edit-record edit-' + key, id);
        if (treePage) { html += action('新增', 'add-child', id); }
        if (page === 'connections') { html += action('测试连接', 'test-saved-connection', id); }
        if (page === 'users') { html += action(item.enabled ? '停用' : '启用', 'toggle-user', id); }
        else { html += action('删除', 'delete-record delete-' + key, id); }
        html += '</td></tr>';
      });
      if (!rows.length) { html += '<tr><td colspan="' + (visibleFields.length + 1) + '" class="empty-list"><i class="far fa-folder-open" aria-hidden="true"></i><p>暂无符合条件的' + entity + '</p></td></tr>'; }
      html += '</tbody></table>';
      $('#' + key + '-list').html(html);
      $('#record-count').text(items.length + ' 项');
      $('#list-summary').text('共 ' + items.length + ' 项，符合条件 ' + matching.length + ' 项');
    }
    function fillDepartments(selector, exclude) {
      var select = $(selector).empty().append($('<option>').val('').text(selector === '#user-scopes' ? '请选择部门（科室）' : '无（顶级部门）'));
      var excluded = exclude ? descendantCodes(departments, exclude) : new Set();
      ordered(departments, function (a, b) { return a.position - b.position; }).forEach(function (row) {
        if (!excluded.has(row.item.code)) { select.append($('<option>').val(row.item.code).text('　'.repeat(row.depth) + row.item.name + (row.item.enabled ? '' : '（停用）'))); }
      });
    }
    function renderDepartmentTree() {
      var query = $('#department-search').val().trim().toLowerCase();
      var found = new Set();
      departments.forEach(function (item) {
        if (!query || item.name.toLowerCase().includes(query)) { found.add(item.code); var parent = item.parent; while (parent && !found.has(parent)) { found.add(parent); var row = byCode(departments, parent); parent = row ? row.parent : null; } }
      });
      function branch(parent) {
        var container = $('<ul>');
        departments.filter(function (item) { return (item.parent || null) === parent && found.has(item.code); }).forEach(function (item) {
          var node = $('<li>'), select = $('<button type="button" class="department-node">').attr('data-code', item.code).toggleClass('selected', selectedDepartment === item.code).append('<i class="far fa-folder mr-2" aria-hidden="true"></i>').append(document.createTextNode(item.name));
          var children = branch(item.code);
          if (children.children().length) { node.append($('<details open>').append($('<summary>').append(select)).append(children)); }
          else { node.append(select); }
          container.append(node);
        });
        return container;
      }
      $('#department-tree').empty().append(branch(null));
      if (!departments.length) { $('#department-tree').append('<p class="text-muted">暂无部门，请先新增部门</p>'); }
    }
    function load() {
      $('#refresh-management').prop('disabled', true);
      var url = '/api/admin/' + page;
      if (page === 'users') {
        $.when(api('/api/admin/user-options'), api(url)).done(function (options, users) {
          departments = options.scopes; roles = options.roles; items = users;
          $('#user-roles').empty().append($('<option>').val('').text('请选择角色'));
          roles.forEach(function (role) { $('#user-roles').append($('<option>').val(role.id).text(role.name + (role.enabled ? '' : '（停用）'))); });
          fillDepartments('#user-scopes'); renderDepartmentTree(); render();
        }).always(function () { $('#refresh-management').prop('disabled', false); });
      } else {
        api(url).done(function (data) { items = page === 'roles' ? data.roles : data; if (page === 'departments') { departments = items; } render(); }).always(function () { $('#refresh-management').prop('disabled', false); });
        if (page === 'menus') { api('/api/admin/menu-options').done(function (data) { menuOptions = data; }); }
      }
    }
    function openForm(item, parent) {
      editing = item || null;
      $('#' + key + '-form')[0].reset(); $('#form-message').empty();
      $('#edit-title').text((item ? '编辑' : '新增') + entity);
      $('#' + key + '-enabled').prop('checked', item ? item.enabled : true);
      if (page === 'connections') {
        var defaults = {name:'', engine:'oracle', mode:'tcp', host:'127.0.0.1', port:1521, namespace:'', username:'',
          local_instance:'', service_kind:'service_name', service_value:'', oracle_driver:'thick', oracle_client_dir:'', auth_type:'password', schema:''};
        $.each(defaults, function (field, defaultValue) { $('#connection-' + field.replace(/_/g, '-')).val(item && item[field] !== undefined ? item[field] : defaultValue); });
        $('#connection-password').val('').attr('placeholder', item && item.has_password ? '已保存密码，留空保留' : '请输入数据库密码');
        $('#connection-encrypt').prop('checked', item ? item.encrypt : true);
        $('#connection-trust-certificate').prop('checked', item ? item.trust_certificate : false);
        $('#connection-test-result').empty().removeClass(); connectionFields();
      } else if (page === 'users') {
        $('#user-id').val(item ? item.id : ''); $('#user-name').val(item ? item.username : '').prop('readonly', !!item);
        $('#user-nickname').val(item ? item.nickname : ''); $('#user-contact').val(item ? item.contact : '');
        $('#user-password').prop('required', !item).attr('minlength', '6').attr('placeholder', '6–128 字符，编辑时留空保留');
        $('#user-roles').val(item && item.role_ids.length ? String(item.role_ids[0]) : '');
        $('#user-scopes').val(item && item.scopes.length ? item.scopes[0] : '');
        $('#legacy-user-note').text(item && (item.role_ids.length > 1 || item.scopes.length > 1) ? '此账号存在历史多角色或多部门配置，保存后将按当前选择更新为单角色、单部门。' : '用户部门仅用于组织管理，不限制 SQL 查询结果。');
      } else if (page === 'roles') {
        $('#role-id').val(item ? item.id : ''); $('#role-name').val(item ? item.name : ''); $('#role-code').val(item ? item.code : ''); $('#role-remark').val(item ? item.remark : '');
      } else if (page === 'departments') {
        fillDepartments('#department-parent', item ? item.code : null); $('#department-parent').val(item ? item.parent || '' : parent || '');
        $('#department-code').val(item ? item.code : '').prop('readonly', !!item); $('#department-name').val(item ? item.name : '');
        $('#department-position').val(item ? item.position : 0); $('#department-remark').val(item ? item.remark : '');
      } else if (page === 'menus') {
        $('#menu-kind').val(item ? (item.parent ? 'page' : 'directory') : (parent ? 'page' : 'directory')).prop('disabled', !!item);
        $('#menu-parent').empty().append($('<option>').val('').text('请选择上级目录'));
        items.filter(function (menu) { return !menu.parent; }).forEach(function (menu) { $('#menu-parent').append($('<option>').val(menu.code).text(menu.title)); });
        $('#menu-parent').val(item ? item.parent || '' : parent || '');
        $('#menu-page').empty().append($('<option>').val('').text('请选择工作页面'));
        var choices = item && item.parent ? [{code:item.code, title:item.title}] : menuOptions;
        choices.forEach(function (option) { $('#menu-page').append($('<option>').val(option.code).text(option.title)); });
        $('#menu-page').val(item && item.parent ? item.code : '').prop('disabled', !!item);
        $('#menu-code').val(item ? item.code : ''); $('#menu-title').val(item ? item.title : ''); $('#menu-position').val(item ? item.position : 0);
        menuKind();
      }
      $('#edit-modal').modal('show');
    }
    function menuKind() {
      var leaf = $('#menu-kind').val() === 'page';
      $('#menu-parent,#menu-page').closest('.form-group').toggle(leaf);
      $('#menu-parent,#menu-page').prop('required', leaf);
      $('#menu-code').prop('readonly', !!editing || leaf);
    }
    function save(event) {
      event.preventDefault(); var data, id, method = editing ? 'PUT' : 'POST', url;
      if (page === 'connections') { id = editing ? editing.id : null; data = connectionData(); }
      else if (page === 'users') {
        id = $('#user-id').val();
        data = {username:$('#user-name').val(), nickname:$('#user-nickname').val(), contact:$('#user-contact').val(), password:$('#user-password').val(),
          role_ids:$('#user-roles').val() ? [Number($('#user-roles').val())] : [], scopes:$('#user-scopes').val() ? [$('#user-scopes').val()] : []};
      } else if (page === 'roles') { id = $('#role-id').val(); data = {name:$('#role-name').val(), code:$('#role-code').val(), remark:$('#role-remark').val()}; }
      else if (page === 'departments') { id = $('#department-code').val(); data = {code:id, name:$('#department-name').val(), parent:$('#department-parent').val() || null, position:Number($('#department-position').val()), remark:$('#department-remark').val()}; }
      else { id = $('#menu-code').val(); data = {code:id, title:$('#menu-title').val(), parent:$('#menu-kind').val() === 'page' ? $('#menu-parent').val() : null, position:Number($('#menu-position').val())}; }
      data.enabled = $('#' + key + '-enabled').prop('checked');
      url = page === 'departments' && !editing ? '/api/admin/scopes' : '/api/admin/' + page + (editing ? '/' + encodeURIComponent(id) : '');
      var submit = $(event.currentTarget).find('[type="submit"]').prop('disabled', true);
      api(url, method, data).then(function (saved) {
        if (page === 'connections' && data.engine === 'oracle') { editing = saved; return api('/api/admin/connections/' + saved.id + '/test', 'POST', {}); }
        return null;
      }).done(function (result) { $('#edit-modal').modal('hide'); load(); message(result ? result.message : entity + '已保存', !result || (result.persisted && result.status === 'PASSED')); }).fail(function () {
        $('#form-message').attr('class', 'alert alert-danger').text($('#message').text());
      }).always(function () { submit.prop('disabled', false); });
    }

    if (page === 'authorization') { initAuthorization(); return; }
    fields[page].forEach(function (field, index) {
      $('#sort-field').append($('<option>').val(field[0]).text(field[1]));
      $('#column-options').append($('<label class="column-option">').append($('<input type="checkbox" checked>').val(field[0]).prop('disabled', index === 0)).append(document.createTextNode(field[1])));
    });
    $('#sort-field').val(treePage ? 'position' : 'id');
    $('#sort-field,#sort-direction').on('change', render);
    $('.sort-menu,.column-menu').on('click', function (event) { event.stopPropagation(); });
    $('#column-options').on('change', 'input', function () { if (this.checked) { hiddenColumns.delete(this.value); } else { hiddenColumns.add(this.value); } render(); });
    $(document).on('click', '.sort-heading', function () { var field = $(this).data('field'); $('#sort-direction').val($('#sort-field').val() === field && $('#sort-direction').val() === 'asc' ? 'desc' : 'asc'); $('#sort-field').val(field); render(); });
    $('#management-filter').on('submit', function (event) { event.preventDefault(); filters = {name:$('#filter-name').val().trim(), contact:$('#filter-contact').val() || '', status:$('#filter-status').val(), engine:$('#filter-engine').val() || ''}; render(); });
    $('#reset-filter').on('click', function () { $('#management-filter')[0].reset(); filters = {name:'', contact:'', status:''}; selectedDepartment = ''; $('#department-search').val(''); if (page === 'users') { renderDepartmentTree(); } render(); });
    $('#refresh-management').on('click', load);
    $('#new-' + key).on('click', function () { openForm(); });
    $('#' + key + '-form').on('submit', save);
    $('#edit-modal').on('shown.bs.modal', function () { $(this).find('input:not([type="hidden"]):not([readonly])').first().trigger('focus'); });
    $(document).on('click', '.edit-record', function () { var id = String($(this).data('id')); openForm(items.find(function (item) { return String(treePage ? item.code : item.id) === id; })); });
    $(document).on('click', '.add-child', function () { var item = byCode(items, String($(this).data('id'))); openForm(null, page === 'menus' && item.parent ? item.parent : item.code); });
    $(document).on('click', '.delete-record', function () { var id = $(this).data('id'); if (window.confirm('确认删除此' + entity + '？')) { api('/api/admin/' + page + '/' + encodeURIComponent(id), 'DELETE').done(function () { load(); message(entity + '已删除', true); }); } });
    $(document).on('click', '.toggle-user', function () { var id = Number($(this).data('id')), item = items.find(function (user) { return user.id === id; }); if (window.confirm('确认' + (item.enabled ? '停用' : '启用') + '此用户？')) { api('/api/admin/users/' + id, 'PUT', {enabled:!item.enabled}).done(load); } });
    $(document).on('click', '.tree-toggle', function () { var id = String($(this).data('id')); if (collapsed.has(id)) { collapsed.delete(id); } else { collapsed.add(id); } render(); });
    $('#expand-tree').on('click', function () { if (collapsed.size) { collapsed.clear(); } else { items.forEach(function (item) { collapsed.add(item.code); }); } render(); });
    $('#department-search').on('input', renderDepartmentTree);
    $('#department-tree').on('click', '.department-node', function (event) { event.preventDefault(); selectedDepartment = $(this).attr('data-code'); $('#department-tree .department-node').removeClass('selected'); $(this).addClass('selected'); render(); });
    $('#clear-department').on('click', function () { selectedDepartment = ''; renderDepartmentTree(); render(); });
    $('#menu-kind').on('change', function () { menuKind(); if (!editing) { $('#menu-code').val($('#menu-kind').val() === 'page' ? $('#menu-page').val() : ''); } });
    $('#menu-page').on('change', function () { var code = $(this).val(), option = menuOptions.find(function (item) { return item.code === code; }); $('#menu-code').val(code); if (option) { $('#menu-title').val(option.title); } });
    $('#connection-port').attr({min:'1',max:'65535'}); $('#connection-password').attr('autocomplete','new-password');
    $('#connection-engine').on('change', function () { $('#connection-port').val({oracle:1521, mysql:3306, sqlserver:1433}[$(this).val()]); $('#connection-auth-type').val('password'); $('#connection-test-result').empty().removeClass(); connectionFields(); });
    $('#connection-mode,#connection-auth-type,#connection-oracle-driver').on('change', connectionFields);
    $('#connection-form').on('input change', 'input,select', function () { $('#connection-test-result').empty().removeClass(); });
    $('#test-connection-draft').on('click', function () {
      if (!$('#connection-form')[0].reportValidity()) { return; }
      var button = $(this).prop('disabled', true).text('测试中…');
      $('#connection-test-result').attr('class','alert alert-info').text('正在登录数据库并执行只读探测…');
      var data = connectionData(), fingerprint = JSON.stringify(data);
      api('/api/admin/connections/test', 'POST', data).done(function (result) {
        if (JSON.stringify(connectionData()) !== fingerprint) { $('#connection-test-result').attr('class','alert alert-warning').text('参数已变更，请重新测试当前配置'); return; }
        $('#connection-test-result').attr('class', 'alert alert-' + (result.status === 'PASSED' ? 'success' : 'danger')).text(result.message + '（' + result.elapsed_ms + ' ms）');
      }).fail(function () { $('#connection-test-result').attr('class', 'alert alert-danger').text($('#message').text()); }).always(function () { button.prop('disabled', false).text('测试连接'); });
    });
    $(document).on('click', '.test-saved-connection', function () {
      var button = $(this).prop('disabled', true).text('测试中…');
      api('/api/admin/connections/' + $(this).attr('data-id') + '/test', 'POST', {}).done(function (result) { load(); message(result.persisted ? result.message + '（' + result.elapsed_ms + ' ms）' : '配置已变更或删除，请重新测试当前连接', result.persisted && result.status === 'PASSED'); }).always(function () { button.prop('disabled', false).text('测试连接'); });
    });
    load();

    function connectionFields() {
      var engine = $('#connection-engine').val(), local = $('#connection-mode').val() === 'local', windows = engine === 'sqlserver' && $('#connection-auth-type').val() === 'windows';
      function show(id, visible) { $(id).closest('.form-group').toggle(visible); }
      show('#connection-host', !local); $('#connection-host').prop('required', !local);
      show('#connection-local-instance', local && engine !== 'mysql');
      show('#connection-service-kind', engine === 'oracle'); show('#connection-service-value', engine === 'oracle'); show('#connection-oracle-driver', engine === 'oracle');
      show('#connection-oracle-client-dir', engine === 'oracle' && $('#connection-oracle-driver').val() === 'thick');
      $('#connection-form button[type="submit"]').text(engine === 'oracle' ? '保存并测试' : '保存');
      show('#connection-auth-type', engine === 'sqlserver'); show('#connection-schema', engine === 'sqlserver');
      show('#connection-username', !windows); show('#connection-password', !windows);
      $('#connection-username').prop('required', !windows); $('#connection-password').prop('required', !windows && !(editing && editing.has_password && editing.engine === engine));
      $('.connection-tls').toggle(engine !== 'oracle'); $('#trust-certificate-label').toggle(engine === 'sqlserver');
      $('label[for="connection-namespace"]').text(engine === 'oracle' ? '命名空间（Schema，可选）' : '命名空间（数据库名称）');
      $('#connection-namespace').prop('required', engine !== 'oracle');
      $('#connection-local-instance').attr('placeholder', engine === 'oracle' ? 'TNS 别名，可留空使用本机端口' : 'localhost\\SQLEXPRESS 或 (localdb)\\MSSQLLocalDB');
      $('#connection-hint').text(engine === 'oracle' ? 'Oracle 11g 使用 Thick 和 64 位 Instant Client，可在上方指定客户端目录或留空使用环境配置。Thin 不需要客户端目录，仅支持 Oracle 12.1 及以上。本地服务可填 TNS 别名；留空时使用本机端口和所选服务名 / SID。' : engine === 'mysql' ? '本地模式通过 127.0.0.1 和端口连接本机 MySQL 实例；命名空间填写数据库名称。TLS 默认校验证书。' : 'SQL Server 需要 Microsoft ODBC Driver 18 或 17。本地实例可留空使用本机端口；Windows 身份验证使用运行服务的系统账号。');
    }
    function connectionData() {
      var data = {};
      ['name','engine','mode','host','namespace','username','password','local_instance','service_kind','service_value','oracle_driver','oracle_client_dir','auth_type','schema'].forEach(function (field) { data[field] = $('#connection-' + field.replace(/_/g, '-')).val(); });
      data.port = Number($('#connection-port').val()); data.encrypt = $('#connection-encrypt').prop('checked'); data.trust_certificate = $('#connection-trust-certificate').prop('checked'); data.enabled = $('#connection-enabled').prop('checked');
      if (editing) { data.id = editing.id; data.revision = editing.revision; }
      return data;
    }

    function initAuthorization() {
      var authorizationRoles = [];
      function syncChecks() {
        $('.menu-group').each(function () {
          var children = $(this).closest('details').find('.menu-check'), checked = children.filter(':checked').length;
          $(this).prop('checked', children.length > 0 && checked === children.length).prop('indeterminate', checked > 0 && checked < children.length);
        });
        var leaves = $('.menu-check'), checked = leaves.filter(':checked').length;
        $('#check-all-menus').prop('checked', leaves.length > 0 && checked === leaves.length).prop('indeterminate', checked > 0 && checked < leaves.length);
      }
      api('/api/admin/menu-authorization').done(function (data) {
        authorizationRoles = data.roles;
        data.roles.forEach(function (role) { $('#authorization-role').append($('<option>').val(role.id).text(role.name)); });
        data.menus.filter(function (menu) { return !menu.parent; }).forEach(function (group) {
          var details = $('<details class="authorization-group" open>'), summary = $('<summary>');
          summary.append($('<label>').append('<input type="checkbox" class="menu-group">').append(document.createTextNode(group.title + (group.enabled ? '' : '（停用）'))));
          details.append(summary); var children = $('<ul>');
          data.menus.filter(function (menu) { return menu.parent === group.code; }).forEach(function (menu) {
            children.append($('<li>').append($('<label>').append($('<input type="checkbox" class="menu-check">').val(menu.code)).append(document.createTextNode(menu.title + (menu.enabled && group.enabled ? '' : '（停用）')))));
          });
          details.append(children); $('#menu-checks').append(details);
        });
        $('#authorization-role').trigger('change');
      });
      $('#authorization-role').on('change', function () {
        var id = Number($(this).val()), role = authorizationRoles.find(function (row) { return row.id === id; });
        $('.menu-check').each(function () { $(this).prop('checked', !!role && role.menu_ids.includes(this.value)); }); syncChecks();
      });
      $('#menu-checks').on('change', '.menu-check', syncChecks).on('change', '.menu-group', function () { $(this).closest('details').find('.menu-check').prop('checked', this.checked); syncChecks(); });
      $('#check-all-menus').on('change', function () { $('.menu-check').prop('checked', this.checked); syncChecks(); });
      $('#expand-authorization').on('click', function () { var details = $('#menu-checks details'); details.prop('open', details.filter('[open]').length !== details.length); });
      $('#authorization-form').on('submit', function (event) {
        event.preventDefault(); var id = Number($('#authorization-role').val()), values = $('.menu-check:checked').map(function () { return this.value; }).get();
        var submit = $(this).find('[type="submit"]').prop('disabled', true);
        api('/api/admin/roles/' + id + '/menus', 'PUT', {menu_ids:values}).done(function () { var role = authorizationRoles.find(function (row) { return row.id === id; }); if (role) { role.menu_ids = values; } message('菜单授权已保存并立即生效', true); }).always(function () { submit.prop('disabled', false); });
      });
    }
  };
})(jQuery);
