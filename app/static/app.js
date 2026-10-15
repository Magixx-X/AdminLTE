(function ($) {
  'use strict';
  var csrf = $('meta[name="csrf-token"]').attr('content'), page = $('body').data('page');
  var taskStatus = {PENDING:'排队中',RUNNING:'执行中',SUCCEEDED:'成功',FAILED:'失败',CANCELLED:'已取消',INTERRUPTED:'已中断',EXPIRED:'已过期',DELETED:'已删除',DRAFT:'草稿',REVIEW:'审核中',PUBLISHED:'已发布',DISABLED:'已停用'};
  var templates = [], activeTemplate = null, currentGroup = null, taskIds = [], grid = null, editor = null, pollTimer = null;
  var historyStart = 0, auditStart = 0;
  var settingLabels = {MAX_MONTHS:'最多查询月份数',QUERY_TIMEOUT:'默认查询超时（秒）',QUEUE_LIMIT:'等待队列容量',MAX_PAGE_SIZE:'每页最多行数',MAX_PREVIEW_ROWS:'单任务预览最多行数',MAX_EXPORT_ROWS:'单文件最多导出行数',MAX_EXPORT_BYTES:'单文件最大字节数',EXPORT_TTL:'导出文件有效期（秒）'};
  function esc(v) { return $('<div>').text(v == null ? '' : String(v)).html(); }
  function message(text, good) { $('#message').attr('class','alert alert-' + (good ? 'success':'danger')).text(text); }
  function api(url, method, data) {
    var deferred = $.Deferred();
    $.ajax({url:url,method:method || 'GET',contentType:'application/json',data:data == null ? undefined:JSON.stringify(data),headers:{'X-CSRF-Token':csrf},timeout:15000}).done(function (r) {
      if (r.success) { deferred.resolve(r.data); } else { message(r.error.message); deferred.reject(r); }
    }).fail(function (xhr) {
      var err = xhr.responseJSON && xhr.responseJSON.error;
      message(err ? err.message : '网络请求失败，请检查服务连接后重试');
      if (xhr.status === 401 && page !== 'login') { window.top.location.href = '/login'; }
      deferred.reject(xhr);
    });
    return deferred.promise();
  }
  function table(selector, items, fields, actions) {
    var h = '<table class="table table-sm table-striped table-bordered"><thead><tr>';
    $.each(fields,function(_,f){h += '<th>' + esc(f[1]) + '</th>';});
    if(actions){h += '<th>操作</th>';}
    h += '</tr></thead><tbody>';
    $.each(items,function(_,item){h += '<tr>';$.each(fields,function(_,f){var v=item[f[0]];if(f[0]==='status'){v=taskStatus[v] || v;}if(typeof v==='object'){v=JSON.stringify(v);}h += '<td>' + esc(v) + '</td>';});if(actions){h += '<td>' + actions(item) + '</td>';}h += '</tr>';});
    h += '</tbody></table>'; $(selector).html(items.length ? h : '<p class="text-muted">暂无记录</p>');
  }
  function button(label, cls, id) { return '<button type="button" class="btn btn-sm btn-outline-primary ' + cls + '" data-id="' + esc(id) + '">' + esc(label) + '</button>'; }
  function dateMonth(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth()+1)).slice(-2); }
  function shortcut(n) {var end=new Date(),start;if(n===0){end.setMonth(end.getMonth()-1,1);start=new Date(end.getFullYear(),end.getMonth(),1);}else{start=new Date(end.getFullYear(),end.getMonth()-n+1,1);}$('#month-start').val(dateMonth(start));$('#month-end').val(dateMonth(end));}
  function renderParams() {
    $('#parameters').empty();
    $('#template-description').text(activeTemplate ? activeTemplate.description : '请选择已发布、已授权的模板');
    $.each(activeTemplate ? activeTemplate.schema : [],function(_,spec){
      var div=$('<div class="col-md-4 mb-3">'),id='param-'+spec.name,input;
      div.append($('<label>').attr('for',id).text((spec.label || spec.name) + (spec.required ? ' *':'')));
      if(spec.type==='select' || spec.type==='multiselect') {
        input=$('<select class="form-control">');if(spec.type==='multiselect'){input.prop('multiple',true);}else{input.append($('<option>').val('').text('不限 / 未选择'));}
        $.each(spec.choices,function(_,v){input.append($('<option>').val(v).text(v));});
      } else if(spec.type==='boolean') { input=$('<select class="form-control"><option value="">不限</option><option value="true">是</option><option value="false">否</option></select>'); }
      else {var type={integer:'number',decimal:'number',date:'date',datetime:'datetime-local',month:'month'}[spec.type] || 'text';input=$('<input class="form-control">').attr('type',type);if(spec.type==='decimal'){input.attr('step','any');}if(spec.max_length){input.attr('maxlength',spec.max_length);}if(spec.min!=null){input.attr('min',spec.min);}if(spec.max!=null){input.attr('max',spec.max);}}
      input.attr({id:id,name:spec.name}).prop('required',!!spec.required);if(spec.default!=null){input.val(spec.default);}div.append(input);$('#parameters').append(div);
    });
  }
  function loadTemplates(manage) {return api('/api/templates' + (manage ? '?manage=1&q=' + encodeURIComponent($('#template-search').val() || ''):'')).done(function(data){templates=data;if(manage){table('#template-list',data,[['id','ID'],['name','名称'],['category','分类'],['status','状态'],['latest_version','版本']],function(t){return button('编辑','edit-template',t.id);});}else{$('#template-select').find('option:not(:first)').remove();$.each(data,function(_,t){$('#template-select').append($('<option>').val(t.id).text(t.name));});}});}
  function showResult(tid) {
    api('/api/queries/'+tid).done(function(task){
      if(grid){grid.destroy();grid=null;}$('#results').empty();
      $('#result-notice').text(task.truncated ? '结果达到预览上限；完整导出受独立配额控制。' : '预览结果短期保存在 Worker 内存；正式 SQL 应具备稳定排序。');
      if(!task.columns.length){$('#result-notice').text('查询成功，无符合条件的结果');return;}
      var cols=[];$.each(task.columns,function(i,c){cols.push({title:c,data:i,orderable:$.inArray(c.toLowerCase(),$.map(activeTemplate ? activeTemplate.sort_fields:[],function(x){return x.toLowerCase();}))>=0,render:$.fn.dataTable.render.text()});});
      grid=$('#results').DataTable({processing:true,serverSide:true,searching:false,pageLength:100,lengthChange:false,scrollX:true,order:[],columns:cols,language:{emptyTable:'没有符合条件的数据',processing:'加载中…',info:'第 _START_–_END_ 行，共 _TOTAL_ 行',infoEmpty:'暂无数据',paginate:{next:'下一页',previous:'上一页'},zeroRecords:'没有结果'},ajax:function(req,callback){var url='/api/queries/'+tid+'/results?start='+req.start+'&length='+req.length+'&draw='+req.draw;if(req.order.length){url+='&sort='+encodeURIComponent(task.columns[req.order[0].column].toLowerCase())+'&direction='+req.order[0].dir;}api(url).done(function(data){callback(data);}).fail(function(){callback({draw:req.draw,data:[],recordsTotal:0,recordsFiltered:0});});}});
    });
  }
  function pollQueries() {
    if(!taskIds.length){return;}api('/api/queries/history?group_id='+encodeURIComponent(currentGroup)).done(function(data){
      var tasks=data.items,finished=true,success=true;
      $.each(tasks,function(_,t){if(t.status==='PENDING'||t.status==='RUNNING'){finished=false;}if(t.status!=='SUCCEEDED'){success=false;}});
      table('#query-tasks',tasks,[['month','月份'],['status','状态'],['row_count','预览行数'],['duration','耗时（秒）'],['error','提示']],function(t){return t.status==='SUCCEEDED' ? button('查看结果','show-results',t.id):((t.status==='PENDING'||t.status==='RUNNING') ? button('取消','cancel-query',t.id):'');});
      $('#export-group').prop('disabled',!success || !tasks.length);
      if(!finished){pollTimer=setTimeout(pollQueries,1000);}else{$('#execute').prop('disabled',false);}
    }).fail(function(){$('#execute').prop('disabled',false);});
  }
  function exportGroup(group) {api('/api/exports','POST',{group_id:group}).done(function(r){message('导出任务已提交：'+r.id,true);var timer=setInterval(function(){api('/api/exports/'+r.id).done(function(e){if(e.status!=='PENDING' && e.status!=='RUNNING'){clearInterval(timer);if(e.status==='SUCCEEDED'){message('导出已生成，可在导出记录下载',true);}else{message(e.error || taskStatus[e.status]);}}}).fail(function(){clearInterval(timer);});},1500);});}
  function templateBody(){return {name:$('#template-name').val(),category:$('#template-category').val(),description:$('#description').val(),sql:editor.getValue(),schema:JSON.parse($('#schema').val()),sort_fields:JSON.parse($('#sort-fields').val()),scope_policy:JSON.parse($('#scope-policy').val()),summary:$('#summary').val(),expected_version:Number($('#template-version').val())};}
  function editTemplate(t){$('#template-id').val(t ? t.id:'');$('#template-version').val(t ? t.latest_version:'');$('#template-name').val(t ? t.name:'');$('#template-category').val(t ? t.category:'报表');$('#description').val(t ? t.description:'');editor.setValue(t ? t.sql:'SELECT record_id, department FROM hospital_approved_view\nWHERE department = :scope_department\nAND visit_time >= :begin_time AND visit_time < :end_time\nORDER BY record_id');$('#schema').val(JSON.stringify(t ? t.schema:[],null,2));$('#sort-fields').val(JSON.stringify(t ? t.sort_fields:['record_id']));$('#scope-policy').val(JSON.stringify(t ? t.scope_policy:{kind:'department_bind'}));$('#summary').val('');$('#scope-reviewed,#all-scope-reviewed,#hospital-validated').prop('checked',false);$('#versions-content').text('');}
  function selectedId(){var id=$('#template-id').val();if(!id){message('请先选择并保存模板');return null;}return id;}
  function loadHistory(){var q=$('#history-filter').serialize();api('/api/queries/history?'+q+'&start='+historyStart).done(function(d){$('#history-total').text('共 '+d.total+' 项；从 '+(historyStart+1)+' 开始');table('#history',d.items,[['id','任务 ID'],['month','月份'],['template_id','模板'],['status','状态'],['duration','秒'],['row_count','预览行数'],['created_at','UTC 时间'],['error','错误摘要']],function(t){return button('详情','task-detail',t.id)+button('再执行','retry-task',t.id)+(t.status==='PENDING'||t.status==='RUNNING' ? button('取消','cancel-query',t.id):'')+(t.status==='SUCCEEDED' ? button('导出批次','export-task',t.group_id):'');});});}
  function loadExports(){api('/api/exports').done(function(d){table('#export-list',d,[['id','导出 ID'],['status','状态'],['row_count','行数'],['size','字节'],['expires','到期 UTC 秒'],['error','错误']],function(e){return e.status==='SUCCEEDED' ? '<a class="btn btn-sm btn-success" href="/api/exports/'+esc(e.id)+'/download">下载</a>'+button('删除','delete-export',e.id):'';});});}
  function loadGrants(){api('/api/admin/grants').done(function(d){table('#grant-list',d,[['template_id','模板 ID'],['user_id','用户 ID'],['role_id','角色 ID'],['execute','允许访问']],function(p){return button('编辑','edit-grant',p.id);});$('#grant-list').data('items',d);});}
  var platformLabels={SESSION_SECONDS:'登录有效期（秒）',LOGIN_LIMIT:'允许连续登录失败次数',LOGIN_WINDOW:'登录失败限制窗口（秒）',DISK_WARNING_BYTES:'磁盘预警阈值（字节）'};
  function settingsUrl(){return page==='settings' ? '/api/admin/settings':'/api/admin/query-settings';}
  function loadSettings(){api(settingsUrl()).done(function(d){$('#settings-fields').empty();$.each(d,function(k,v){if(page==='settings' && !platformLabels[k]){return;}var div=$('<div class="col-md-6 mb-3">');div.append($('<label>').attr('for','setting-'+k).text(platformLabels[k] || settingLabels[k] || k));div.append($('<input type="number" class="form-control" required>').attr({name:k,id:'setting-'+k}).val(v));$('#settings-fields').append(div);});});}
  function health(){api('/api/admin/health').done(function(d){$('#health').text(JSON.stringify(d,null,2));});}
  function loadAudits(){api('/api/admin/audits?'+$('#audit-filter').serialize()+'&start='+auditStart).done(function(d){$('#audit-total').text('共 '+d.total+' 项；从 '+(auditStart+1)+' 开始');table('#audit-list',d.items,[['id','ID'],['timestamp','UTC 时间'],['user_id','用户'],['action','事件'],['template_id','模板'],['version_id','版本'],['task_id','任务'],['result','结果'],['duration','耗时'],['row_count','行数'],['detail','非敏感摘要']]);});}
  function loadDashboard(){api('/api/dashboard').done(function(d){$('#stats').empty();$.each([['SUCCEEDED','成功','success'],['FAILED','失败','danger'],['RUNNING','运行','info'],['PENDING','排队','warning']],function(_,s){$('#stats').append('<div class="col-sm-3"><div class="small-box bg-'+s[2]+'"><div class="inner"><h3>'+esc(d.stats[s[0]] || 0)+'</h3><p>'+s[1]+'</p></div></div></div>');});$('#service').text('Worker：'+(d.worker && new Date().getTime()/1000-d.worker.timestamp<20 ? '在线':'未启动 / 心跳过期'));table('#recent',d.recent,[['month','月份'],['status','状态'],['row_count','行数'],['created_at','UTC 时间']]);});api('/api/templates').done(function(d){$('#favorites').empty();$.each(d,function(_,t){$('#favorites').append($('<a class="btn btn-outline-primary mr-2 mb-2">').attr('href','/pages/query?template_id='+t.id).text(t.name));});if(!d.length){$('#favorites').text('暂无授权模板，请联系管理员');}});}
  $(document).on('click','.cancel-query',function(){api('/api/queries/'+$(this).data('id')+'/cancel','POST',{}).done(function(){message('已请求取消',true);if(page==='history'){loadHistory();}else{pollQueries();}});});
  $(document).on('click','.show-results',function(){showResult($(this).data('id'));});
  $(document).on('click','.reload',function(){if(page==='exports'){loadExports();}if(page==='dashboard'){loadDashboard();}});
  if(page==='login'){if(window.location.search.indexOf('password_changed=1')>=0){message('密码已修改，请使用新密码登录',true);}$('#login-form').on('submit',function(e){e.preventDefault();api('/api/auth/login','POST',{username:$('#username').val(),password:$('#password').val()}).done(function(){window.top.location.href='/';});});return;}
  if(page==='shell'){
    var workspace=$('.content-wrapper'),tabKey='information-tabs-'+$('.wrapper').data('user-id');
    // Bootstrap fade callbacks can reactivate an old pane after a fast iframe tab switch.
    var framePrototype=$.fn.IFrame.Constructor.prototype, switchFrameTab=framePrototype.switchTab;
    framePrototype.switchTab=function(){workspace.find('.tab-pane').removeClass('fade');return switchFrameTab.apply(this,arguments);};
    workspace.on('shown.bs.tab',function(){var url=$('.tab-pane.active iframe').attr('src');$('.nav-sidebar a').each(function(){if($(this).attr('href')===url){$(this).parents('.has-treeview').addClass('menu-open').children('.nav-treeview').show();}});});
    function rememberTabs(){var urls=$('.tab-pane iframe').map(function(){return $(this).attr('src');}).get(),active=$('.tab-pane.active iframe').attr('src');try{sessionStorage.setItem(tabKey,JSON.stringify({urls:urls,active:active}));}catch(ignore){}}
    $('#logout').on('click',function(){api('/api/auth/logout','POST',{}).done(function(){try{sessionStorage.removeItem(tabKey);}catch(ignore){}window.top.location.href='/login';});});
    $('#refresh-tab').on('click',function(){var frame=$('.tab-pane.active iframe')[0];if(frame){frame.contentWindow.location.reload();}});
    $(window).on('load',function(){
      var saved;try{saved=JSON.parse(sessionStorage.getItem(tabKey) || 'null');}catch(ignore){}
      var links=[],activeLink=null;
      if(saved && $.isArray(saved.urls)){$.each(saved.urls.slice(0,30),function(_,url){$('.nav-sidebar a,#open-profile').each(function(){if(typeof url==='string' && url.indexOf('/pages/')===0 && $(this).attr('href')===url && $.inArray(this,links)<0){links.push(this);if(saved.active===url){activeLink=this;}}});});}
      function observe(){new MutationObserver(rememberTabs).observe(workspace[0],{childList:true,subtree:true,attributes:true,attributeFilter:['class']});rememberTabs();}
      function restoreNext(){if(links.length){var link=links.shift();workspace.one('shown.bs.tab',function(){setTimeout(restoreNext,0);});$(link).trigger('click');}else{if(activeLink){$(activeLink).trigger('click');}observe();}}
      restoreNext();
    });return;
  }
  if(page==='profile'){
    $('#profile-form').on('submit',function(e){e.preventDefault();var submit=$(this).find('[type=submit]').prop('disabled',true);api('/api/auth/profile','PUT',{nickname:$('#profile-nickname').val(),contact:$('#profile-contact').val()}).done(function(){message('个人资料已保存',true);try{$(window.top.document).find('#account-menu').text($('#profile-nickname').val().trim() || $('#profile-username').val());}catch(ignore){}}).always(function(){submit.prop('disabled',false);});});
    $('#password-form').on('submit',function(e){e.preventDefault();if($('#new-password').val()!==$('#confirm-password').val()){message('两次输入的新密码不一致');return;}var submit=$(this).find('[type=submit]').prop('disabled',true);api('/api/auth/password','POST',{current_password:$('#current-password').val(),new_password:$('#new-password').val(),confirm_password:$('#confirm-password').val()}).done(function(){$('#password-form')[0].reset();window.top.location.href='/login?password_changed=1';}).always(function(){submit.prop('disabled',false);});});
    return;
  }
  api('/api/auth/me').done(function(me){csrf=me.csrf_token;if($.inArray('template:approve',me.permissions)<0){$('#publish-template,#disable-template').hide();}if($.inArray('result:export',me.permissions)<0){$('#export-group').hide();}});
  if($.inArray(page,['users','roles','menus','departments','connections','authorization'])>=0){window.managementPage(page,api,message,esc);return;}
  if(page==='dashboard'){loadDashboard();}
  if(page==='query'){
    shortcut(1);loadTemplates(false).done(function(){var match=window.location.search.match(/template_id=(\d+)/);if(match){$('#template-select').val(match[1]).trigger('change');}});
    $('#template-select').on('change',function(){var id=Number($(this).val());activeTemplate=null;$.each(templates,function(_,t){if(t.id===id){activeTemplate=t;}});renderParams();});
    $('#month-shortcuts button').on('click',function(){shortcut(Number($(this).data('months')));});
    $('#clear-template').on('click',function(){$('#template-select').val('').trigger('change');});
    $('#reset-params').on('click',function(){renderParams();shortcut(1);});
    $('#reset-all').on('click',function(){$('#template-select').val('').trigger('change');shortcut(1);if(grid){grid.destroy();grid=null;}$('#results,#query-tasks').empty();currentGroup=null;taskIds=[];clearTimeout(pollTimer);$('#execute').prop('disabled',false);$('#export-group').prop('disabled',true);});
    $('#query-form').on('submit',function(e){e.preventDefault();if(!activeTemplate){message('请选择模板');return;}var params={month_start:$('#month-start').val(),month_end:$('#month-end').val()};$.each(activeTemplate.schema,function(_,s){params[s.name]=$('#param-'+s.name).val();});$('#execute').prop('disabled',true);api('/api/queries','POST',{template_id:activeTemplate.id,params:params}).done(function(d){currentGroup=d.group_id;taskIds=d.task_ids;pollQueries();}).fail(function(){$('#execute').prop('disabled',false);});});
    $('#export-group').on('click',function(){exportGroup(currentGroup);});
  }
  if(page==='templates'){
    editor=CodeMirror.fromTextArea(document.getElementById('sql'),{lineNumbers:true,mode:'text/x-plsql',indentUnit:2});loadTemplates(true);editTemplate(null);
    $('#template-search').on('input',function(){loadTemplates(true);});$('#new-template').on('click',function(){editTemplate(null);});
    $(document).on('click','.edit-template',function(){var id=Number($(this).data('id'));$.each(templates,function(_,t){if(t.id===id){editTemplate(t);}});});
    $('#template-form').on('submit',function(e){e.preventDefault();try{var data=templateBody(),id=$('#template-id').val();api('/api/templates'+(id ? '/'+id:''),id ? 'PUT':'POST',data).done(function(t){editTemplate(t);loadTemplates(true);message('新版本已保存',true);});}catch(err){message('JSON 格式错误：'+err.message);}});
    $('#copy-template').on('click',function(){var id=selectedId();if(id){api('/api/templates','POST',{name:$('#template-name').val()+'（副本）',category:$('#template-category').val(),copy_from:Number(id)}).done(function(t){loadTemplates(true);editTemplate(t);});}});
    $.each(['submit','publish','disable'],function(_,action){$('#'+action+'-template').on('click',function(){var id=selectedId();if(id){api('/api/templates/'+id+'/'+action,'POST',{scope_reviewed:$('#scope-reviewed').prop('checked'),all_scope_reviewed:$('#all-scope-reviewed').prop('checked'),hospital_validated:$('#hospital-validated').prop('checked'),evidence:$('#evidence').val()}).done(function(){loadTemplates(true);message('模板状态已更新',true);});}});});
    $('#delete-template').on('click',function(){var id=selectedId();if(id && window.confirm('确认软删除模板？历史版本仍保留。')){api('/api/templates/'+id,'DELETE').done(function(){loadTemplates(true);editTemplate(null);});}});
    $('#versions').on('click',function(){var id=selectedId();if(id){api('/api/templates/'+id+'/versions').done(function(d){$('#versions-content').text(JSON.stringify(d,null,2));});}});
  }
  if(page==='history'){loadHistory();$('#history-filter').on('submit',function(e){e.preventDefault();historyStart=0;loadHistory();});$('#history-prev').on('click',function(){historyStart=Math.max(0,historyStart-100);loadHistory();});$('#history-next').on('click',function(){historyStart+=100;loadHistory();});$(document).on('click','.task-detail',function(){api('/api/queries/'+$(this).data('id')).done(function(d){$('#task-detail').text(JSON.stringify(d,null,2));});});$(document).on('click','.retry-task',function(){api('/api/queries/'+$(this).data('id')+'/retry','POST',{}).done(function(){loadHistory();message('已重新提交任务',true);});});$(document).on('click','.export-task',function(){exportGroup($(this).data('id'));});}
  if(page==='exports'){loadExports();$(document).on('click','.delete-export',function(){api('/api/exports/'+$(this).data('id'),'DELETE').done(loadExports);});}
  if(page==='settings' || page==='query_settings'){loadSettings();$('#settings-form').on('submit',function(e){e.preventDefault();var d={};$('#settings-fields input').each(function(){d[this.name]=Number(this.value);});api(settingsUrl(),'PUT',d).done(function(){message('设置已保存',true);});});}
  if(page==='grants'){
    var grantOptions={};
    function grantTargets(){var key=$('#grant-kind').val()==='role_id' ? 'roles':'users';$('#grant-target').empty();$.each(grantOptions[key] || [],function(_,x){$('#grant-target').append($('<option>').val(x.id).text(x.name));});}
    api('/api/admin/grant-options').done(function(d){grantOptions=d;$.each(d.templates,function(_,t){$('#grant-template').append($('<option>').val(t.id).text(t.name));});grantTargets();loadGrants();});$('#grant-kind').on('change',grantTargets);
    $('#grant-form').on('submit',function(e){e.preventDefault();var allowed=$('#grant-allowed').prop('checked'),d={template_id:Number($('#grant-template').val()),execute:allowed,view:allowed,export:allowed};d[$('#grant-kind').val()]=Number($('#grant-target').val());api('/api/admin/grants','POST',d).done(function(){loadGrants();message('模板授权已保存',true);});});
    $(document).on('click','.edit-grant',function(){var id=Number($(this).data('id'));$.each($('#grant-list').data('items'),function(_,p){if(p.id===id){$('#grant-template').val(p.template_id);$('#grant-kind').val(p.user_id ? 'user_id':'role_id').trigger('change');$('#grant-target').val(p.user_id || p.role_id);$('#grant-allowed').prop('checked',p.execute && p.view && p.export);}});});
  }
  if(page==='monitor'){
    function loadMonitor(){api('/api/admin/monitor').done(function(d){var labels={database:'元数据库',users:'用户数量',active_sessions:'有效会话',worker:'后台任务服务',free_disk_bytes:'可用磁盘字节',disk_warning:'磁盘预警',environment:'环境',source:'查询任务数据源',connection_tests:'连接配置测试'},rows=[];$.each(d,function(k,v){rows.push({name:labels[k] || k,value:k==='source' ? (v==='mock' ? 'Mock 开发模式 · 合成数据，Oracle 与医院 SQL 待验收':'Oracle · 内网'):v});});table('#platform-status',rows,[['name','指标'],['value','当前状态']]);});}
    loadMonitor();$('#monitor-refresh').on('click',loadMonitor);$('#health-check').on('click',health);
  }
  if(page==='about'){api('/api/about').done(function(d){table('#about-platform',d.platform,[['name','程序 / 组件'],['version','版本']]);$.each(['production','development'],function(_,k){table('#about-'+k,d[k],[['name','程序'],['version','锁定版本'],['installed','当前环境安装版本']]);});});}
  if(page==='audits'){loadAudits();$('#audit-filter').on('submit',function(e){e.preventDefault();auditStart=0;loadAudits();});$('#audit-prev').on('click',function(){auditStart=Math.max(0,auditStart-100);loadAudits();});$('#audit-next').on('click',function(){auditStart+=100;loadAudits();});}
  $(window).on('unload',function(){clearTimeout(pollTimer);});
})(jQuery);
