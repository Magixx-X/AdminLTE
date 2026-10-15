(function ($) {
  'use strict';
  var csrf = $('meta[name="csrf-token"]').attr('content'), page = $('body').data('page');
  var taskStatus = {PENDING:'排队中',RUNNING:'执行中',SUCCEEDED:'成功',FAILED:'失败',CANCELLED:'已取消',INTERRUPTED:'已中断',EXPIRED:'已过期',DELETED:'已删除',DRAFT:'草稿',REVIEW:'审核中',PUBLISHED:'可查询',DISABLED:'已停用'};
  var templates = [], activeTemplate = null, currentGroup = null, taskIds = [], grid = null, editor = null, pollTimer = null;
  var historyStart = 0, auditStart = 0;
  var activeTaskId = null, loadedTaskId = null, taskStates = {}, viewSequence = 0;
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
  function dateMonth(d) {return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2);}
  function rangePair() {
    var schema=activeTemplate ? activeTemplate.schema:[], candidates=schema.filter(function(s){return s.end_after && s.split_by_month!==false;}), explicit=candidates.filter(function(s){return s.split_by_month===true;});
    var end=explicit.length===1 ? explicit[0]:candidates.length===1 ? candidates[0]:null;
    return end ? {start:schema.find(function(s){return s.name===end.end_after;}),end:end}:null;
  }
  function shortcut(n) {
    var pair=rangePair();if(!pair){return;}var now=new Date(),end=new Date(now.getFullYear(),now.getMonth()+(n===0 ? 0:1),1),start=new Date(now.getFullYear(),now.getMonth()-(n===0 ? 1:n-1),1);
    function format(d){var value=dateMonth(d);return pair.start.type==='month' ? value:value+'-01'+(pair.start.type==='datetime' ? 'T00:00':'');}
    $('#param-'+pair.start.name).val(format(start));$('#param-'+pair.end.name).val(format(end));
  }
  function renderParams() {
    $('#parameters').empty();$('#template-description').text(activeTemplate ? activeTemplate.description:'请选择模板');
    $.each(activeTemplate ? activeTemplate.schema:[],function(_,spec){
      var div=$('<div class="col-md-4 mb-3">'),id='param-'+spec.name,input;
      div.append($('<label>').attr('for',id).text(spec.label || spec.name));
      if(spec.type==='select' || spec.type==='multiselect' || spec.type==='boolean'){
        input=$('<select class="form-control">');if(spec.type==='multiselect'){input.prop('multiple',true);}if(!spec.required){input.append($('<option>').val('').text('请选择'));}
        $.each(spec.type==='boolean' ? ['true','false']:spec.choices,function(_,value){input.append($('<option>').val(value).text(value==='true' ? '是':value==='false' ? '否':value));});
      }else{input=$('<input class="form-control">').attr('type',spec.type==='date' ? 'date':spec.type==='datetime' ? 'datetime-local':spec.type==='month' ? 'month':spec.type==='integer' || spec.type==='decimal' ? 'number':'text');if(spec.type==='decimal'){input.attr('step','any');}if(spec.min!=null){input.attr('min',spec.min);}if(spec.max!=null){input.attr('max',spec.max);}if(spec.max_length){input.attr('maxlength',spec.max_length);}}
      input.attr({id:id,name:spec.name}).prop('required',!!spec.required);if(spec.default!=null){input.val(spec.default);}div.append(input);$('#parameters').append(div);
    });
    var pair=rangePair();$('#date-shortcuts').toggle(!!pair);
    if(pair && !$('#param-'+pair.start.name).val() && !$('#param-'+pair.end.name).val()){shortcut(1);}
  }
  function loadTemplates(manage) {return api('/api/templates' + (manage ? '?manage=1&q=' + encodeURIComponent($('#template-search').val() || ''):'')).done(function(data){templates=data;if(manage){table('#template-list',data,[['id','ID'],['name','名称'],['category','分类'],['status','状态'],['latest_version','版本']],function(t){return button('编辑','edit-template',t.id);});}else{$('#template-select').find('option:not(:first)').remove();$.each(data,function(_,t){$('#template-select').append($('<option>').val(t.id).text(t.name));});}});}
  function clearResults() {
    clearTimeout(pollTimer);viewSequence++;if(grid){grid.destroy();grid=null;}$('#results,#query-tasks,#result-month-tabs').empty();$('#result-notice').empty();currentGroup=null;taskIds=[];activeTaskId=null;loadedTaskId=null;taskStates={};$('#execute').prop('disabled',false);$('#export-group').prop('disabled',true);
  }
  function showResult(tid) {
    var sequence=++viewSequence;loadedTaskId=tid;
    if(grid){grid.destroy();grid=null;}$('#results').empty();$('#result-notice').text('正在加载结果…');
    api('/api/queries/'+tid).done(function(task){
      if(sequence!==viewSequence || activeTaskId!==tid){return;}
      $('#result-notice').text(task.truncated ? '结果达到预览上限；导出将重新查询完整结果。':'结果短期保存在后台任务服务内存中。');
      if(!task.columns.length){$('#result-notice').text('查询成功，无符合条件的数据');return;}
      var cols=[];$.each(task.columns,function(i,c){cols.push({title:c,data:i,orderable:$.inArray(c.toLowerCase(),$.map(activeTemplate ? activeTemplate.sort_fields:[],function(x){return x.toLowerCase();}))>=0,render:$.fn.dataTable.render.text()});});
      grid=$('#results').DataTable({processing:true,serverSide:true,searching:false,pageLength:100,lengthChange:false,scrollX:true,order:[],columns:cols,language:{emptyTable:'没有符合条件的数据',processing:'加载中…',info:'第 _START_–_END_ 行，共 _TOTAL_ 行',infoEmpty:'暂无数据',paginate:{next:'下一页',previous:'上一页'},zeroRecords:'没有结果'},ajax:function(req,callback){var url='/api/queries/'+tid+'/results?start='+req.start+'&length='+req.length+'&draw='+req.draw;if(req.order.length){url+='&sort='+encodeURIComponent(task.columns[req.order[0].column].toLowerCase())+'&direction='+req.order[0].dir;}api(url).done(function(data){if(sequence===viewSequence){callback(data);}}).fail(function(){if(sequence===viewSequence){callback({draw:req.draw,data:[],recordsTotal:0,recordsFiltered:0});}});}});
    }).fail(function(){if(sequence===viewSequence){loadedTaskId=null;$('#result-notice').text($('#message').text());}});
  }
  function activateResult(tid) {
    activeTaskId=tid;$('#result-month-tabs button').each(function(){var selected=$(this).data('id')===tid;$(this).toggleClass('active',selected).attr({'aria-selected':String(selected),tabindex:selected ? '0':'-1'});});
    var task=taskStates[tid];if(!task){return;}
    if(task.status==='SUCCEEDED'){if(loadedTaskId!==tid){showResult(tid);}return;}
    viewSequence++;loadedTaskId=null;if(grid){grid.destroy();grid=null;}$('#results').empty();$('#result-notice').text(task.error || '当前任务：'+(taskStatus[task.status] || task.status));
  }
  function pollQueries() {
    if(!taskIds.length){return;}var group=currentGroup;
    api('/api/queries/history?group_id='+encodeURIComponent(group)).done(function(data){
      if(group!==currentGroup){return;}var tasks=data.items.sort(function(a,b){return a.month.localeCompare(b.month);}),finished=true,success=true;
      taskStates={};var tabs=$('#result-month-tabs').empty();
      $.each(tasks,function(_,t){taskStates[t.id]=t;if(t.status==='PENDING'||t.status==='RUNNING'){finished=false;}if(t.status!=='SUCCEEDED'){success=false;}tabs.append($('<button type="button" role="tab" class="nav-link result-month">').attr({'data-id':t.id,'aria-controls':'query-result-panel'}).text((t.month==='result' ? '查询结果':t.month)+' · '+(taskStatus[t.status] || t.status)));});
      table('#query-tasks',tasks,[['month','月份'],['status','状态'],['row_count','预览行数'],['duration','耗时（秒）'],['error','提示']],function(t){return t.status==='PENDING'||t.status==='RUNNING' ? button('取消','cancel-query',t.id):'';});
      if(!activeTaskId || !taskStates[activeTaskId]){activeTaskId=tasks.length ? tasks[0].id:null;}if(activeTaskId){activateResult(activeTaskId);}
      $('#export-group').prop('disabled',!success || !tasks.length);
      if(!finished){pollTimer=setTimeout(pollQueries,1000);}else{$('#execute').prop('disabled',false);}
    }).fail(function(){if(group===currentGroup){$('#execute').prop('disabled',false);}});
  }
  function exportGroup(group) {api('/api/exports','POST',{group_id:group}).done(function(r){message('导出任务已提交：'+r.id,true);var timer=setInterval(function(){api('/api/exports/'+r.id).done(function(e){if(e.status!=='PENDING' && e.status!=='RUNNING'){clearInterval(timer);if(e.status==='SUCCEEDED'){message('导出已生成，可在导出记录下载',true);}else{message(e.error || taskStatus[e.status]);}}}).fail(function(){clearInterval(timer);});},1500);});}
  function templateBody(){return {name:$('#template-name').val(),category:$('#template-category').val(),description:$('#description').val(),sql:editor.getValue(),schema:JSON.parse($('#schema').val()),sort_fields:JSON.parse($('#sort-fields').val()),summary:$('#summary').val(),expected_version:Number($('#template-version').val())};}
  function editTemplate(t){$('#template-id').val(t ? t.id:'');$('#template-version').val(t ? t.latest_version:'');$('#template-name').val(t ? t.name:'');$('#template-category').val(t ? t.category:'报表');$('#description').val(t ? t.description:'');editor.setValue(t ? t.sql:'SELECT record_id, department FROM hospital_approved_view\nWHERE visit_time >= :start_date AND visit_time < :end_date\nORDER BY record_id');$('#schema').val(JSON.stringify(t ? t.schema:[{name:'start_date',label:'开始日期（包含）',type:'date',required:true},{name:'end_date',label:'结束日期（不含）',type:'date',required:true,end_after:'start_date'}],null,2));$('#sort-fields').val(JSON.stringify(t ? t.sort_fields:['record_id']));$('#summary').val(t ? t.summary:'');$('#versions-content').text('');}
  function templatesChanged(id){window.top.dispatchEvent(new CustomEvent('query-template-saved',{detail:{id:id}}));}
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
  api('/api/auth/me').done(function(me){csrf=me.csrf_token;if($.inArray('result:export',me.permissions)<0){$('#export-group').hide();}});
  if($.inArray(page,['users','roles','menus','departments','connections','authorization'])>=0){window.managementPage(page,api,message,esc);return;}
  if(page==='dashboard'){loadDashboard();}
  if(page==='query'){
    function refreshAfterSave(event){var selected=$('#template-select').val();loadTemplates(false).done(function(){$('#template-select').val(selected);if(Number(selected)===event.detail.id){$('#template-select').trigger('change');}});}
    window.top.addEventListener('query-template-saved',refreshAfterSave);
    $(window).on('unload',function(){window.top.removeEventListener('query-template-saved',refreshAfterSave);});
    loadTemplates(false).done(function(){var match=window.location.search.match(/template_id=(\d+)/);if(match){$('#template-select').val(match[1]).trigger('change');}});
    $('#template-select').on('change',function(){clearResults();var id=Number($(this).val());activeTemplate=templates.find(function(t){return t.id===id;}) || null;renderParams();});
    $('#date-shortcuts button').on('click',function(){shortcut(Number($(this).data('months')));});
    $('#result-month-tabs').on('click','.result-month',function(){activateResult($(this).data('id'));}).on('keydown','.result-month',function(e){var buttons=$(this).parent().find('button'),index=buttons.index(this);if(e.key==='ArrowRight'){index=(index+1)%buttons.length;}else if(e.key==='ArrowLeft'){index=(index+buttons.length-1)%buttons.length;}else if(e.key==='Home'){index=0;}else if(e.key==='End'){index=buttons.length-1;}else{return;}e.preventDefault();buttons.eq(index).trigger('focus').trigger('click');});
    $('#clear-template,#reset-all').on('click',function(){$('#template-select').val('').trigger('change');});
    $('#reset-params').on('click',function(){clearResults();renderParams();});
    $('#query-form').on('submit',function(e){e.preventDefault();if(!activeTemplate){message('请选择模板');return;}clearResults();var params={};$.each(activeTemplate.schema,function(_,spec){params[spec.name]=$('#param-'+spec.name).val();});$('#execute').prop('disabled',true);api('/api/queries','POST',{template_id:activeTemplate.id,params:params}).done(function(d){currentGroup=d.group_id;taskIds=d.task_ids;pollQueries();}).fail(function(){$('#execute').prop('disabled',false);});});
    $('#export-group').on('click',function(){exportGroup(currentGroup);});
  }
  if(page==='templates'){
    editor=CodeMirror.fromTextArea(document.getElementById('sql'),{lineNumbers:true,mode:'text/x-plsql',indentUnit:2});loadTemplates(true);editTemplate(null);
    $('#template-search').on('input',function(){loadTemplates(true);});$('#new-template').on('click',function(){editTemplate(null);});
    $(document).on('click','.edit-template',function(){var id=Number($(this).data('id'));$.each(templates,function(_,t){if(t.id===id){editTemplate(t);}});});
    $('#template-form').on('submit',function(e){e.preventDefault();try{var data=templateBody(),id=$('#template-id').val();api('/api/templates'+(id ? '/'+id:''),id ? 'PUT':'POST',data).done(function(t){editTemplate(t);loadTemplates(true);templatesChanged(t.id);message('模板已保存，可直接查询',true);});}catch(err){message('JSON 格式错误：'+err.message);}});
    $('#copy-template').on('click',function(){var id=selectedId();if(id){api('/api/templates','POST',{name:$('#template-name').val()+'（副本）',category:$('#template-category').val(),copy_from:Number(id)}).done(function(t){loadTemplates(true);editTemplate(t);templatesChanged(t.id);});}});
    $('#disable-template').on('click',function(){var id=selectedId();if(id){api('/api/templates/'+id+'/disable','POST',{}).done(function(){loadTemplates(true);templatesChanged(Number(id));message('模板已停用；重新保存可启用',true);});}});
    $('#delete-template').on('click',function(){var id=selectedId();if(id && window.confirm('确认软删除模板？历史版本仍保留。')){api('/api/templates/'+id,'DELETE').done(function(){loadTemplates(true);editTemplate(null);templatesChanged(Number(id));});}});
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
