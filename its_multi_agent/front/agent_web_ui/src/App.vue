<template>
  <div class="app-container">
    <!-- 登录页面 -->
    <div v-if="!isLoggedIn" class="login-container">
      <form class="login-form" @submit.prevent="handleLogin" novalidate>
        <div class="its-logo-flat login-logo">
            <img src="/its-logo.svg" alt="知行 Logo" width="60" height="60"/>
          </div>
        <h1 class="login-title">{{ isRegistering ? '注册客户端账号' : '知行系统登录' }}</h1>
        <div class="login-input-group">
          <label for="username">用户名</label>
          <input 
            id="username"
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            @keyup.enter="handleLogin"
          />
        </div>
        <div v-if="isRegistering" class="login-input-group">
          <label for="confirm-password">确认密码</label>
          <input
            id="confirm-password"
            v-model="confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            @keyup.enter="handleLogin"
          />
        </div>
        <div class="login-input-group">
          <label for="password">密码</label>
          <input 
            id="password"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </div>
        <div v-if="loginError" class="login-error">
          {{ loginError }}
        </div>
        <button class="login-button btn-primary" type="submit">
          {{ isRegistering ? '注册并进入' : '登录' }}
        </button>
        <button class="login-mode-button" type="button" @click.prevent="toggleRegisterMode">
          {{ isRegistering ? '已有账号，返回登录' : '注册客户端账号' }}
        </button>
      </form>
    </div>
    
    <!-- 主界面（登录后显示） -->
    <template v-else>
      <!-- 移除header部分，将用户信息移到结果框右上角 -->
      
      <div class="main-content">
        <!-- 左侧历史会话列表 - 可展开收起 -->
        <button v-if="isMobile && isSidebarExpanded" class="sidebar-backdrop" aria-label="关闭侧边栏" @click="closeMobileSidebar"></button>
        <div id="workspace-sidebar" class="sidebar-wrapper" role="navigation" aria-label="工作区导航" v-show="!isMobile || isSidebarExpanded">
          <!-- 侧边栏内容 -->
          <div class="sidebar-content" :class="{ 'expanded': isSidebarExpanded }">
            <!-- 扁平化Logo和ITS标题 -->
            <div class="app-branding">
              <!-- 扁平风格的Logo -->
              <div class="its-logo-flat">
                <img src="/its-logo.svg" alt="知行 Logo" width="40" height="40"/>
              </div>
              <div v-show="isSidebarExpanded" class="brand-copy">
                <strong>知行</strong>
                <span>智能服务助手</span>
              </div>
              
              <!-- 侧边栏展开/收起按钮 - 与logo水平对齐 -->
              <button 
                class="toggle-sidebar-btn" 
                @click="toggleSidebar"
                :aria-expanded="isSidebarExpanded"
                aria-controls="workspace-sidebar"
                :aria-label="isSidebarExpanded ? '收起侧边栏' : '展开侧边栏'"
                :title="isSidebarExpanded ? '收起侧边栏' : '展开侧边栏'"
              >
                <PanelLeftClose v-if="isSidebarExpanded" :size="18" /><PanelLeftOpen v-else :size="18" />
              </button>
            </div>
            
            <!-- 新建会话按钮 - 放到logo下方并左右拉伸 -->
            <div class="session-button-container" v-show="isSidebarExpanded">
              <a href="/" class="new-chat-btn" @click.prevent="createNewSession">
                <span class="icon">
                  <SquarePen :size="18" aria-hidden="true" />
                </span>
                <span class="text">新建会话</span>

              </a>
            </div>
            
            <!-- 导航栏 -->
              <div class="navigation-container" v-show="isSidebarExpanded">
              <div class="sidebar-section-label">工作区</div>
              <div v-if="projects.length" class="project-selector">
                <span class="project-label"><FolderKanban :size="15" aria-hidden="true" />当前工作区 <button class="workspace-add" type="button" title="新建工作区" aria-label="新建工作区" @click.stop="showWorkspaceCreate = !showWorkspaceCreate"><Plus :size="14" /></button></span>
                <select v-model="selectedProjectId" :disabled="isProcessing" aria-label="当前项目">
                  <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
                </select>
                <button
                  v-if="selectedProjectId && selectedProjectId !== 'default'"
                  class="workspace-delete"
                  type="button"
                  title="删除当前工作区"
                  aria-label="删除当前工作区"
                  :disabled="isProcessing || deletingWorkspaceId === selectedProjectId"
                  @click.stop="deleteCurrentWorkspace"
                ><Trash2 :size="15" aria-hidden="true" /></button>
                <span v-if="workspaceDeleteError" class="workspace-create-error" role="alert">{{ workspaceDeleteError }}</span>
                <form v-if="showWorkspaceCreate" class="workspace-create" @submit.prevent="createWorkspace">
                  <input v-model.trim="workspaceName" maxlength="64" placeholder="工作区名称" aria-label="工作区名称" autofocus />
                  <div class="workspace-create-actions"><button type="submit" :disabled="!workspaceName">创建</button><button type="button" @click="showWorkspaceCreate = false">取消</button></div>
                  <span v-if="workspaceCreateError" class="workspace-create-error">{{ workspaceCreateError }}</span>
                </form>
              </div>
              <label class="mode-selector">
                <span class="project-label"><SlidersHorizontal :size="15" aria-hidden="true" />工作模式</span>
                <select v-model="workMode" :disabled="isProcessing" aria-label="工作模式">
                  <option v-for="mode in workModes" :key="mode.value" :value="mode.value">{{ mode.label }}</option>
                </select>
              </label>
              <div class="navigation-item" :class="{ 'selected': selectedNavItem === 'knowledge' }" @click="handleKnowledgeBase">
                <BookOpen :size="18" class="nav-icon" aria-hidden="true" />
                <span class="nav-text">知识库查询</span>
              </div>
              <div class="navigation-item" :class="{ 'selected': selectedNavItem === 'memory' }" @click="handleMemory">
                <Brain :size="18" class="nav-icon" aria-hidden="true" />
                <span class="nav-text">长期记忆</span>
              </div>
              <div class="navigation-item" :class="{ 'selected': selectedNavItem === 'files' }" @click="handleFiles">
                <FileText :size="18" class="nav-icon" aria-hidden="true" />
                <span class="nav-text">生成文件</span>
              </div>
              <button class="tools-toggle" type="button" :class="{ selected: selectedNavItem === 'tools' }" @click="handleTools">
                <span><Wrench :size="16" aria-hidden="true" />工具与插件</span>
                <span class="tools-entry-count">{{ enabledPlugins.length }}</span>
              </button>
            </div>

            <!-- 历史会话列表 - 仅在展开状态显示 -->
            <div v-show="isSidebarExpanded" class="sidebar-main">
              <div class="navigation-item" @click="toggleSessions">
                <History :size="18" class="nav-icon" aria-hidden="true" />
                <span class="nav-text">历史会话</span>
              </div>
              <div class="sessions-list" v-show="showSessions">
                <div v-if="isLoadingSessions" class="loading-sessions">
                  加载历史对话中...
                </div>
                <div v-else-if="sessions.length === 0" class="no-sessions">
                  暂无历史对话
                </div>
                <div
                  v-for="session in sessions"
                  :key="session.session_id"
                  :class="['session-item', { 'selected': session.session_id === selectedSessionId }]"
                  @click="selectSession(session.session_id)"
                >
                  <div class="session-info">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <MessageSquare :size="16" class="history-icon" aria-hidden="true" />
                      <div class="session-preview" :title="session.title || session.memory?.[0]?.content || '空对话'">{{ session.title || session.memory?.[0]?.content || '空对话' }}</div>
                      <span v-if="session.unread_tasks" class="session-unread" title="后台任务已完成">{{ session.unread_tasks }}</span>
                    </div>
                  </div>
                  <button
                    class="session-delete-button"
                    type="button"
                    :aria-label="`删除会话 ${session.title || session.session_id}`"
                    :title="deletingSessionId === session.session_id ? '删除中...' : '删除会话'"
                    :disabled="deletingSessionId === session.session_id"
                    @click.stop="requestDeleteSession(session.session_id)"
                  >
                    <Trash2 :size="15" aria-hidden="true" />
                  </button>
                  <template v-if="pendingDeleteSessionId === session.session_id">
                    <button class="session-confirm-button" type="button" @click.stop="confirmDeleteSession(session.session_id)">确认删除</button>
                    <button class="session-cancel-button" type="button" @click.stop="cancelDeleteSession">取消</button>
                  </template>
                </div>
                <button v-if="nextSessionPage" class="history-page-button" :disabled="isLoadingSessions" @click="fetchUserSessions(true)">加载更多会话</button>
                <span v-if="sessionListError" class="history-error" role="alert">{{ sessionListError }}</span>
              </div>
            </div>
          </div>
          

        </div>
        
        <!-- 右侧显示区域 -->
        <div class="main-container">
          <!-- 最终结果显示框 -->
          <div class="result-container" :class="{ 'processing': isProcessing }">
            <!-- 顶部区域，包含用户信息 -->
            <div class="top-user-section">
              <button v-if="isMobile" ref="mobileSidebarToggle" class="mobile-sidebar-toggle" aria-label="展开侧边栏" title="展开侧边栏"
                :aria-expanded="isSidebarExpanded" aria-controls="workspace-sidebar" @click="toggleSidebar"><Menu :size="20" aria-hidden="true" /></button>
              <div class="workspace-title"><span class="workspace-eyebrow">知行工作台</span><h1 :title="workspaceTitle">{{ workspaceTitle }}</h1></div>
              <div class="model-selector">
                <label v-if="modelProfiles.length" for="model-profile">模型</label>
                <select v-if="modelProfiles.length" id="model-profile" v-model="selectedModelProfile" :disabled="isProcessing">
                  <option v-for="profile in modelProfiles" :key="profile.id" :value="profile.id">
                    {{ profile.name }}
                  </option>
                </select>
                <button v-if="selectedModelProfile && selectedModelProfile.startsWith('user-')" type="button" class="model-profile-delete" title="删除当前个人模型配置" aria-label="删除当前个人模型配置" :disabled="isProcessing" @click="deleteCurrentModelProfile"><Trash2 :size="15" aria-hidden="true" /></button>
                <button type="button" class="model-config-button" aria-label="模型设置" title="模型设置" :aria-expanded="showModelConfig" @click="showModelConfig = !showModelConfig"><Settings2 :size="18" aria-hidden="true" /></button>
              </div>
              <div v-if="showModelConfig" class="model-config-panel">
                <input v-model="customModel.name" placeholder="配置名称" />
                <input v-model="customModel.model_name" placeholder="模型名称" />
                <input v-model.number="customModel.context_window_tokens" type="number" min="1024" step="1024" aria-label="上下文窗口 token 数" placeholder="上下文窗口 token 数（默认 32768）" />
                <input v-model.number="customModel.max_output_tokens" type="number" min="256" step="256" aria-label="最大输出 token 数" placeholder="最大输出 token 数（默认 4096）" />
                <input v-model="customModel.base_url" placeholder="Base URL" />
                <input v-model="customModel.api_key" type="password" placeholder="API Key" />
                <select v-model="customModelMode"><option value="temporary">仅本次使用</option><option value="saved">保存配置</option></select>
                <button type="button" @click="applyCustomModel">应用模型</button>
                <span v-if="modelConfigMessage">{{ modelConfigMessage }}</span>
              </div>
              <!-- 用户信息和操作按钮 - 放在流程框上方 -->
              <div class="user-avatar-container" ref="avatarContainerRef">
                <!-- 头像，点击时切换用户信息显示状态 -->
                <div
                  class="user-avatar"
                  role="button"
                  aria-label="用户菜单"
                  @click="toggleUserInfo"
                  tabindex="0"
                >{{ currentUser ? currentUser.charAt(0).toUpperCase() : 'U' }}</div>
                
                <!-- 用户信息下拉框，点击头像时显示/隐藏 -->
                <div class="user-info-dropdown" v-show="showUserInfo">
                  <template v-if="currentUser">
                    <span class="user-name">{{ currentUser }}</span>
                    <button data-testid="setup_logout" class="btn-tertiary" style="width: 100%; justify-content: flex-start;" @click="handleLogout"><span role="img" class="semi-icon semi-icon-default text-16"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" fill="none" viewBox="0 0 24 24"><path fill="currentColor" fill-rule="evenodd" d="M14 3H4.5v18H14v-5h2v5a2 2 0 0 1-2 2H4.5a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2H14a2 2 0 0 1 2 2v5h-2zm5.207 4.793a1 1 0 1 0-1.414 1.414L19.586 11H10.5a1 1 0 1 0 0 2h9.086l-1.793 1.793a1 1 0 0 0 1.414 1.414l3.5-3.5a1 1 0 0 0 0-1.414z" clip-rule="evenodd"></path></svg></span>退出登录</button>
                  </template>
                  <template v-else>
                    <span class="user-name">当前未登录</span>
                    <button class="login-button btn-primary" @click="goToLogin">请登录</button>
                  </template>
                </div>
              </div>
            </div>

          
            
            <KnowledgeWorkspace v-if="activeWorkspace === 'knowledge'" />
            <MemoryWorkspace v-else-if="activeWorkspace === 'memory'" :workspace-id="selectedProjectId" />
            <FileArtifactsWorkspace v-else-if="activeWorkspace === 'files'" @preview="openFilePreview" />
            <FilePreviewWorkspace v-else-if="activeWorkspace === 'preview'" :artifact-id="previewArtifactId" @back="closeFilePreview" />
            <ToolsWorkspace v-else-if="activeWorkspace === 'tools'"
              :plugins="plugins" :enabled-ids="enabledPlugins" :confirmed-ids="confirmedPlugins"
              :allowed-ids="pluginWorkspace?.plugins || []" :workspace-name="pluginWorkspace?.name || ''"
              :busy="isProcessing" :loading="isLoadingPlugins" :error="pluginLoadError" :describe="pluginDescription"
              @toggle="toggleOptionalPlugin" @refresh="fetchPlugins(true)" @back="returnToChat" />
            <template v-else>
            <!-- 统一的消息展示区域 -->
            <div class="chat-message-container" ref="processContent">
              <section v-if="sessionTasks.length || taskError || isLoadingTasks" class="task-status-panel" aria-label="后台任务状态">
                <div class="task-status-header">
                  <strong>后台任务</strong>
                  <button type="button" class="task-refresh-button" :disabled="isLoadingTasks" @click="refreshSessionTasks">
                    {{ isLoadingTasks ? '刷新中' : '刷新' }}
                  </button>
                </div>
                <p v-if="taskError" class="task-status-error" role="alert">{{ taskError }}</p>
                <div v-for="task in sessionTasks" :key="task.run_id" class="task-status-row">
                  <div class="task-status-copy">
                    <span class="task-status-name">{{ taskStatusLabel(task.status) }}</span>
                    <small>{{ task.run_id.slice(0, 8) }} · {{ task.packet_count || 0 }} 个事件</small>
                    <span v-if="task.error" class="task-status-error">{{ task.error }}</span>
                  </div>
                  <div class="task-status-actions">
                    <button v-if="taskCanFollow(task)" type="button" class="task-action-button" :disabled="isProcessing" @click="followTask(task)">{{ taskActionLabel(task) }}</button>
                    <button v-if="taskCanResume(task)" type="button" class="task-action-button primary" :disabled="resumingTaskId === task.run_id" @click="resumeTask(task)">
                      {{ resumingTaskId === task.run_id ? '恢复中' : '恢复' }}
                    </button>
                  </div>
                </div>
              </section>
              <div class="history-page-status" v-if="isLoadingMessages || nextBeforeId || messageHistoryError">
                <span v-if="isLoadingMessages" role="status">正在加载消息...</span>
                <button v-else-if="nextBeforeId" class="history-page-button" :disabled="isProcessing" @click="loadOlderMessages">加载更早消息</button>
                <span v-if="messageHistoryError" class="history-error" role="alert">{{ messageHistoryError }}</span>
                <button v-if="messageHistoryError && !isLoadingMessages" class="history-page-button" @click="loadMessagePage(!!nextBeforeId)">重试</button>
              </div>
              <div v-for="(msg, index) in chatMessages" :key="`${selectedSessionId}-${msg.id || 'stream-' + index}`" :class="['message-wrapper', msg.type]">
                 <!-- 消息头/角色标识 -->
                 <div class="message-role-label" v-if="msg.type === 'THINKING'" @click="toggleThinking(index)">
                   <div class="thinking-header">
                     <span class="thinking-text">{{ isProcessing && index === chatMessages.length - 1 ? '思考中...' : '思考过程' }}</span>
                     <svg 
                       xmlns="http://www.w3.org/2000/svg" 
                       width="16" 
                       height="16" 
                       viewBox="0 0 24 24" 
                       fill="none" 
                       stroke="currentColor" 
                       stroke-width="2" 
                       stroke-linecap="round" 
                       stroke-linejoin="round"
                       class="thinking-icon"
                       :class="{ 'collapsed': msg.collapsed }"
                     >
                       <polyline points="6 9 12 15 18 9"></polyline>
                     </svg>
                   </div>
                 </div>
                 
                 <!-- 消息内容 -->
                 <div class="message-content" v-show="msg.type !== 'THINKING' || !msg.collapsed">
                   <TaskProgress v-if="msg.type === 'PLAN'" :plan="msg.plan" />
                   <AnswerMessage v-else-if="msg.type === 'assistant'" :text="msg.content" :sources="msg.sources || []" @preview-file="openFilePreview" />
                   <div v-else class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
                   <button v-if="msg.type === 'THINKING'" type="button" class="manage-tools-link" @click="handleTools">
                     <Wrench :size="14" aria-hidden="true" />选择工具与插件
                   </button>
                   <span v-for="attachment in msg.attachments || []" :key="attachment.id" class="attachment-chip">
                     {{ attachment.name }}
                     <button type="button" class="attachment-remove" title="删除附件" aria-label="删除附件" @click="deleteAttachment(attachment.id)">×</button>
                   </span>
                 </div>
              </div>
            </div>
              
              <!-- 用户输入框 - 移动到最终结果输出框内 -->
              <div class="input-container">
                <div class="textarea-with-button">
                  <div v-if="selectedAttachments.length" class="attachment-list">
                    <span v-for="item in selectedAttachments" :key="item.key" class="attachment-chip">
                      {{ item.file.name }}
                      <button type="button" class="attachment-remove" title="移除附件" aria-label="移除附件" @click="removeSelectedAttachment(item.key)">×</button>
                    </span>
                  </div>
                  <textarea
                    v-model="userInput"
                    placeholder="请输入您的请求..."
                    @keyup.enter.exact="handleSend($event)"
                    :disabled="isProcessing || isLoadingMessages"
                  ></textarea>
                  <input ref="attachmentInputRef" class="attachment-input" type="file" multiple
                    accept=".txt,.md,.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.webp" :disabled="isProcessing"
                    @change="selectAttachments" />
                  <button type="button" class="attachment-button" title="添加文档或图片"
                    :disabled="isProcessing" @click="attachmentInputRef?.click()"><Paperclip :size="18" aria-hidden="true" /></button>
                  <button
                    type="button"
                    class="location-button"
                    :class="{ active: !!currentLocation, locating: isLocating }"
                    :disabled="isProcessing || isLocating"
                    :title="locationButtonTitle"
                    @click="refreshLocation"
                  >
                    <LocateFixed :size="18" aria-hidden="true" />
                  </button>
                  <button 
                    class="send-button btn-primary"
                    :aria-label="isProcessing ? '停止生成' : '发送'"
                    :title="isProcessing ? '停止生成' : '发送'"
                    :class="{ 'cancel-button': isProcessing, 'disabled': !userInput.trim() && !isProcessing }"
                    :disabled="isLoadingMessages || (!userInput.trim() && !isProcessing)"
                    @click="isProcessing ? handleCancel() : handleSend()"
                  >
                    <Square v-if="isProcessing" :size="16" aria-hidden="true" /><ArrowUp v-else :size="20" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
      </template>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from 'vue';
import KnowledgeWorkspace from './components/KnowledgeWorkspace.vue';
import MemoryWorkspace from './components/MemoryWorkspace.vue';
import FileArtifactsWorkspace from './components/FileArtifactsWorkspace.vue';
import FilePreviewWorkspace from './components/FilePreviewWorkspace.vue';
import ToolsWorkspace from './components/ToolsWorkspace.vue';
import { PanelLeftClose, PanelLeftOpen, SquarePen, BookOpen, Brain, MapPin, Search, History, MessageSquare, Menu, Settings2, Paperclip, LocateFixed, ArrowUp, Square, Trash2, FolderKanban, Wrench, ChevronDown, SlidersHorizontal, Plus, FileText, Code2 } from '@lucide/vue';
import AnswerMessage from './components/AnswerMessage.vue';
import TaskProgress from './components/TaskProgress.vue';
import { normalizeSources } from './utils/citations';
import {
  authFetch,
  clearAuthSession,
  getAuthToken,
  readErrorMessage,
  readJsonResponse,
  setAuthSession,
} from './api/auth';
import { renderSafeMarkdown as renderMarkdown } from './utils/markdown';
import { parseSSELine } from './utils/sse';

export default {
  name: 'App',
  components: {
    KnowledgeWorkspace,
    MemoryWorkspace,
    FileArtifactsWorkspace,
    FilePreviewWorkspace,
    ToolsWorkspace,
    PanelLeftClose, PanelLeftOpen, SquarePen, BookOpen, Brain, MapPin, Search, History, MessageSquare, Menu, Settings2, Paperclip, LocateFixed, ArrowUp, Square, Trash2, FolderKanban, Wrench, ChevronDown, SlidersHorizontal, Plus, FileText, Code2,
    AnswerMessage,
    TaskProgress,
  },
  setup() {
    // 登录相关状态
    const isLoggedIn = ref(false);
    // 侧边栏展开/收起状态
    const isMobile = ref(window.innerWidth <= 760);
    const isSidebarExpanded = ref(!isMobile.value);
    const mobileSidebarToggle = ref(null);
    const closeMobileSidebar = () => {
      if (!isMobile.value) return;
      isSidebarExpanded.value = false;
      nextTick(() => mobileSidebarToggle.value?.focus());
    };
    const updateViewport = () => {
      const mobile = window.innerWidth <= 760;
      if (mobile !== isMobile.value) isSidebarExpanded.value = !mobile;
      isMobile.value = mobile;
    };
    const username = ref('');
    const password = ref('');
    const confirmPassword = ref('');
    const isRegistering = ref(false);
    const currentUser = ref('');
    const loginError = ref('');
    const toggleRegisterMode = () => {
      isRegistering.value = !isRegistering.value;
      confirmPassword.value = '';
      loginError.value = '';
    };
    // 用户信息显示状态（用于头像点击显示用户信息）
    const showUserInfo = ref(false);
    // 头像和下拉框的引用
    const avatarContainerRef = ref(null);
    
    // 切换用户信息显示/隐藏
    const toggleUserInfo = () => {
      showUserInfo.value = !showUserInfo.value;
    };

    // 点击外部收起下拉菜单
    const handleClickOutside = (event) => {
      // 关闭用户信息下拉框
      if (showUserInfo.value && avatarContainerRef.value && !avatarContainerRef.value.contains(event.target)) {
        showUserInfo.value = false;
      }
      

    };
    
    // 生命周期钩子：组件挂载后添加事件监听器
    onMounted(() => {
      document.addEventListener('click', handleClickOutside);
      window.addEventListener('auth:unauthorized', handleUnauthorized);
      restoreSession();
    });
    
    // 生命周期钩子：组件卸载前移除事件监听器
    onUnmounted(() => {
      document.removeEventListener('click', handleClickOutside);
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    });
    
    // 恢复当前标签页中的认证会话
    const resetAuthState = () => {
      authGeneration += 1;
      locationGeneration += 1;
      cancelActiveRequest();
      isLoggedIn.value = false;
      currentUser.value = '';
      clearAuthSession();
      username.value = '';
      password.value = '';
      userInput.value = '';
      chatMessages.value = [];
      sessions.value = [];
      selectedSessionId.value = '';
      selectedAttachments.value = [];
      if (attachmentInputRef.value) attachmentInputRef.value.value = '';
      currentLocation.value = null;
      locationError.value = '';
      isLocating.value = false;
      isLoadingSessions.value = false;
      nextSessionPage.value = null;
      nextBeforeId.value = null;
      isLoadingMessages.value = false;
      messageHistoryError.value = '';
      sessionListError.value = '';
      sessionTasks.value = [];
      taskError.value = '';
      modelProfiles.value = [];
      selectedModelProfile.value = '';
      modelConfigMessage.value = '';
      workspaceDeleteError.value = '';
      deletingWorkspaceId.value = '';
      activeTemporaryModel.value = null;
      customModel.value = { name: '', model_name: '', base_url: '', api_key: '', provider: 'openai-compatible', roles: ['reasoning', 'chat'], context_window_tokens: null, max_output_tokens: null };
      customModelMode.value = 'temporary';
      showModelConfig.value = false;
      modelConfigMessage.value = '';
      plugins.value = [];
      isLoadingPlugins.value = false;
      pluginLoadError.value = '';
      projects.value = [];
      selectedProjectId.value = 'default';
      enabledPlugins.value = [];
      confirmedPlugins.value = [];
      showUserInfo.value = false;
      selectedNavItem.value = '';
      activeWorkspace.value = 'chat';
    };

    const restoreSession = async () => {
      if (!getAuthToken()) return;
      const generation = authGeneration;
      try {
        const response = await authFetch('/api/auth/me');
        if (!response.ok) throw new Error('登录状态已失效');
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        currentUser.value = data.user.username;
        isLoggedIn.value = true;
      } catch (error) {
        if (generation === authGeneration) resetAuthState();
      }
    };

    const handleUnauthorized = () => resetAuthState();
    
    // 主界面相关状态
    const userInput = ref('');
    const chatMessages = ref([]); // Unified chat history: user/assistant/THINKING/error
    const processContent = ref(null);
    const isProcessing = ref(false); // 标记是否正在处理请求
    const isLocating = ref(false);
    const currentLocation = ref(null);
    const modelProfiles = ref([]);
    const selectedModelProfile = ref('');
    const showModelConfig = ref(false);
    const customModelMode = ref('temporary');
    const activeTemporaryModel = ref(null);
    const modelConfigMessage = ref('');
    const customModel = ref({ name: '', model_name: '', base_url: '', api_key: '', provider: 'openai-compatible', roles: ['reasoning', 'chat'], context_window_tokens: null, max_output_tokens: null });
    const plugins = ref([]);
    const projects = ref([]);
    const selectedProjectId = ref('default');
    const workMode = ref('auto');
    const showWorkspaceCreate = ref(false);
    const workspaceName = ref('');
    const workspaceCreateError = ref('');
    const workspaceDeleteError = ref('');
    const deletingWorkspaceId = ref('');
    const workModes = [
      { value: 'auto', label: '自动' },
      { value: 'chat', label: '快速对话' },
      { value: 'research', label: '资料研究' },
      { value: 'plan', label: '计划执行' },
    ];
    const enabledPlugins = ref([]);
    const confirmedPlugins = ref([]);
    const isLoadingPlugins = ref(false);
    const pluginLoadError = ref('');
    const selectedAttachments = ref([]);
    const attachmentInputRef = ref(null);
    const locationError = ref('');
    let activeRequest = null;
    let nextRequestId = 0;
    let authGeneration = 0;
    let locationGeneration = 0;
    let sessionGeneration = 0;
    let sessionListRequestId = 0;
    const nextSessionPage = ref(null);
    const nextBeforeId = ref(null);
    const isLoadingMessages = ref(false);
    const messageHistoryError = ref('');
    const sessionListError = ref('');
    const sessionTasks = ref([]);
    const isLoadingTasks = ref(false);
    const taskError = ref('');
    const resumingTaskId = ref('');
    const deletingSessionId = ref('');
    const pendingDeleteSessionId = ref('');
    const cancelActiveRequest = () => {
      const request = activeRequest;
      // 使等待中的定位结果失效，防止取消后写入下一次请求的上下文。
      locationGeneration += 1;
      isLocating.value = false;
      interruptPlan(request);
      if (request?.taskRunId && request.cancelTaskOnStop) {
        void authFetch(`/api/tasks/${encodeURIComponent(request.taskRunId)}/cancel`, {
          method: 'POST',
        }).catch((error) => console.warn('后台任务取消失败:', error));
      }
      activeRequest = null;
      request?.controller.abort();
      void request?.reader?.cancel().catch(() => {});
      isProcessing.value = false;
    };

    // 项目插件清单是后端授权边界。切换项目或发送请求前都重新取交集，
    // 避免把上一个项目选择的插件或确认状态带到当前项目。
    const currentProject = () => projects.value.find(project => project.id === selectedProjectId.value) || null;
    const projectAllowsPlugin = (pluginId) => Boolean(currentProject()?.plugins?.includes(pluginId));
    const pluginWorkspace = computed(() => currentProject());
    const reconcileProjectPlugins = () => {
      const project = currentProject();
      if (!project) {
        enabledPlugins.value = [];
        confirmedPlugins.value = [];
        return;
      }
      const allowed = new Set(project.plugins || []);
      enabledPlugins.value = enabledPlugins.value.filter(pluginId => allowed.has(pluginId));
      confirmedPlugins.value = confirmedPlugins.value.filter(pluginId => allowed.has(pluginId));
    };
    const defaultPluginsForProject = (project) => {
      const allowed = new Set(project?.plugins || []);
      return plugins.value
        .filter(plugin => allowed.has(plugin.id) && plugin.enabled_by_default && !plugin.requires_confirmation)
        .map(plugin => plugin.id);
    };
    const requestPluginSelection = () => {
      const project = currentProject();
      if (!project) return { enabled: [], confirmed: [] };
      const allowed = new Set(project.plugins || []);
      const enabled = enabledPlugins.value.filter(pluginId => allowed.has(pluginId));
      return {
        enabled,
        confirmed: confirmedPlugins.value.filter(pluginId => enabled.includes(pluginId)),
      };
    };

    const detachActiveRequest = () => {
      if (!activeRequest) return;
      activeRequest.detached = true;
      activeRequest = null;
      isProcessing.value = false;
    };

    const interruptPlan = (request) => {
      const message = chatMessages.value.find(m => m.type === 'PLAN' && m.plan.run_id === request?.planId);
      if (message && ['planning', 'running'].includes(message.plan.status)) {
        message.plan.status = 'interrupted';
        message.plan.steps.forEach(s => { if (['running', 'pending'].includes(s.status)) s.status = 'interrupted'; });
      }
    };

    const fetchModelProfiles = async () => {
      const generation = authGeneration;
      try {
        const response = await authFetch('/api/model-profiles');
        if (!response.ok) return;
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        modelProfiles.value = Array.isArray(data.profiles) ? data.profiles : [];
        const availableProfileIds = new Set(modelProfiles.value.map(profile => profile.id));
        if (!modelProfiles.value.length) {
          selectedModelProfile.value = '';
        } else if (!selectedModelProfile.value || !availableProfileIds.has(selectedModelProfile.value)) {
          selectedModelProfile.value = modelProfiles.value[0].id;
        }
      } catch (error) {
        console.warn('读取模型配置失败:', error);
      }
    };

    const fetchPlugins = async (preserveSelection = false) => {
      if (isLoadingPlugins.value || (preserveSelection && isProcessing.value)) return;
      const generation = authGeneration;
      isLoadingPlugins.value = true;
      pluginLoadError.value = '';
      try {
        const response = await authFetch('/api/plugins');
        if (!response.ok) throw new Error(await readErrorMessage(response, '读取工具列表失败'));
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        plugins.value = Array.isArray(data.plugins) ? data.plugins : [];
        // 项目列表与插件列表是两个异步请求；项目尚未加载时不要把全局默认值
        // 写入选择状态，避免随后 reconcile 时因竞态把默认插件全部清空。
        const project = currentProject();
        if (!preserveSelection) {
          if (project) enabledPlugins.value = defaultPluginsForProject(project);
          confirmedPlugins.value = [];
        }
        const known = new Set(plugins.value.map(plugin => plugin.id));
        enabledPlugins.value = enabledPlugins.value.filter(id => known.has(id));
        confirmedPlugins.value = confirmedPlugins.value.filter(id => enabledPlugins.value.includes(id));
        reconcileProjectPlugins();
      } catch (error) {
        if (generation === authGeneration) pluginLoadError.value = error.message || '读取工具列表失败';
      } finally {
        if (generation === authGeneration) isLoadingPlugins.value = false;
      }
    };

    const fetchProjects = async () => {
      const generation = authGeneration;
      try {
        let response = await authFetch('/api/workspaces');
        if (!response.ok) response = await authFetch('/api/projects');
        if (!response.ok) return;
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        projects.value = Array.isArray(data.workspaces) ? data.workspaces : (Array.isArray(data.projects) ? data.projects : []);
        if (!projects.value.some(project => project.id === selectedProjectId.value)) {
          selectedProjectId.value = projects.value[0]?.id || 'default';
        }
        if (!enabledPlugins.value.length && plugins.value.length) {
          enabledPlugins.value = defaultPluginsForProject(currentProject());
        }
        reconcileProjectPlugins();
      } catch (error) { console.warn('读取项目失败:', error); }
    };

    const pluginDescription = (plugin) => ({
      files: '生成并下载文本或静态网页文件',
      coding: '读取、修改代码并运行检查',
    })[plugin.id] || plugin.description;

    const toggleOptionalPlugin = (plugin, event = null) => {
      if (isProcessing.value) return;
      const checked = event ? Boolean(event.target?.checked) : !enabledPlugins.value.includes(plugin.id);
      if (checked && !projectAllowsPlugin(plugin.id)) {
        if (event?.target) event.target.checked = false;
        return;
      }
      if (checked && plugin.requires_confirmation) {
        const accepted = window.confirm(`启用“${plugin.name}”后，Agent 可以执行该能力。确认继续？`);
        if (!accepted) {
          if (event?.target) event.target.checked = false;
          return;
        }
        confirmedPlugins.value = [...new Set([...confirmedPlugins.value, plugin.id])];
      }
      enabledPlugins.value = checked
        ? [...new Set([...enabledPlugins.value, plugin.id])]
        : enabledPlugins.value.filter(id => id !== plugin.id);
      if (!checked) {
        confirmedPlugins.value = confirmedPlugins.value.filter(id => id !== plugin.id);
      }
    };

    const toggleCorePlugin = (pluginId, event) => {
      const plugin = plugins.value.find(item => item.id === pluginId);
      if (!plugin) return;
      toggleOptionalPlugin(plugin, event);
    };

    const createWorkspace = async () => {
      const generation = authGeneration;
      const name = workspaceName.value.trim();
      if (!name) return;
      workspaceCreateError.value = '';
      try {
        const response = await authFetch('/api/workspaces', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name.trim(), description: `${name.trim()} 工作区`, plugins: requestPluginSelection().enabled }) });
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        if (!response.ok) throw new Error(data.detail || '创建工作区失败');
        projects.value = [...projects.value, data];
        selectedProjectId.value = data.id;
        workspaceName.value = '';
        showWorkspaceCreate.value = false;
      } catch (error) {
        if (generation === authGeneration) workspaceCreateError.value = error.message || '创建工作区失败';
      }
    };

    const deleteCurrentWorkspace = async () => {
      const workspaceId = selectedProjectId.value;
      if (!workspaceId || workspaceId === 'default' || deletingWorkspaceId.value) return;
      const workspace = projects.value.find(project => project.id === workspaceId);
      if (!workspace || !window.confirm(`确定删除工作区“${workspace.name}”吗？该工作区下的会话也将无法继续访问。`)) return;
      const generation = authGeneration;
      deletingWorkspaceId.value = workspaceId;
      workspaceDeleteError.value = '';
      try {
        const response = await authFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await readErrorMessage(response, '删除工作区失败'));
        if (generation !== authGeneration) return;
        projects.value = projects.value.filter(project => project.id !== workspaceId);
        cancelActiveRequest();
        sessionGeneration += 1;
        selectedSessionId.value = '';
        chatMessages.value = [];
        sessionTasks.value = [];
        taskError.value = '';
        nextBeforeId.value = null;
        messageHistoryError.value = '';
        selectedProjectId.value = projects.value.some(project => project.id === 'default')
          ? 'default'
          : (projects.value[0]?.id || 'default');
        await fetchProjects();
        await fetchPlugins();
        await fetchUserSessions();
      } catch (error) {
        if (generation === authGeneration) workspaceDeleteError.value = error.message || '删除工作区失败';
      } finally {
        if (generation === authGeneration) deletingWorkspaceId.value = '';
      }
    };

    const applyCustomModel = async () => {
      const generation = authGeneration;
      if (!customModel.value.name || !customModel.value.model_name || !customModel.value.base_url || !customModel.value.api_key) {
        modelConfigMessage.value = '请填写完整模型配置'; return;
      }
      const optionalTokenLimit = (value) => value == null || value === '' ? null : Number(value);
      const modelPayload = {
        ...customModel.value,
        context_window_tokens: optionalTokenLimit(customModel.value.context_window_tokens),
        max_output_tokens: optionalTokenLimit(customModel.value.max_output_tokens),
      };
      if (customModelMode.value === 'saved') {
        const response = await authFetch('/api/model-profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(modelPayload) });
        if (generation !== authGeneration) return;
        if (!response.ok) {
          const message = await readErrorMessage(response, '保存失败');
          if (generation === authGeneration) modelConfigMessage.value = message;
          return;
        }
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        selectedModelProfile.value = data.id;
        await fetchModelProfiles();
        if (generation !== authGeneration) return;
        modelConfigMessage.value = '已保存并应用';
      } else {
        selectedModelProfile.value = ''; activeTemporaryModel.value = modelPayload; modelConfigMessage.value = '已应用，仅本次请求使用';
      }
      showModelConfig.value = false;
    };

    const deleteCurrentModelProfile = async () => {
      const profileId = selectedModelProfile.value;
      if (!profileId || !profileId.startsWith('user-') || isProcessing.value) return;
      const profile = modelProfiles.value.find(item => item.id === profileId);
      if (!profile || !window.confirm(`确定删除模型配置“${profile.name}”吗？`)) return;
      const generation = authGeneration;
      modelConfigMessage.value = '';
      try {
        const response = await authFetch(`/api/model-profiles/${encodeURIComponent(profileId)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await readErrorMessage(response, '删除模型配置失败'));
        if (generation !== authGeneration) return;
        await fetchModelProfiles();
        if (generation === authGeneration) {
          modelConfigMessage.value = '模型配置已删除';
          showModelConfig.value = true;
        }
      } catch (error) {
        if (generation === authGeneration) {
          modelConfigMessage.value = error.message || '删除模型配置失败';
          showModelConfig.value = true;
        }
      }
    };

    const locationButtonTitle = computed(() => {
      if (isLocating.value) return '正在获取当前位置';
      if (currentLocation.value) {
        const accuracy = currentLocation.value.accuracy;
        return accuracy ? `已获取当前位置，精度约 ${Math.round(accuracy)} 米` : '已获取当前位置';
      }
      return locationError.value || '获取当前位置';
    });

    const queryNeedsDeviceLocation = (query) => {
      const text = query.trim();
      if (/(当前位置|我的位置|我现在在哪里|我在哪里|我在哪儿|我在哪|我这里|我这儿|这里|这儿|附近|周边)/i.test(text)) {
        return true;
      }
      if (/从.+?(到|去|前往|出发)/.test(text)) {
        return false;
      }
      return /(怎么去|如何去|导航|路线|距离|多远|多久|想去|前往|服务站|服务中心|维修点|售后)/.test(text);
    };

    const acquireCurrentLocation = async (force = false) => {
      const generation = ++locationGeneration;
      const cached = currentLocation.value;
      if (!force && cached && Date.now() - cached.captured_at <= 5 * 60 * 1000) {
        return cached;
      }
      if (!navigator.geolocation) {
        locationError.value = '当前浏览器不支持设备定位，请在对话中提供出发地';
        return null;
      }

      isLocating.value = true;
      locationError.value = '';
      try {
        const position = await new Promise((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 30000,
          });
        });
        if (generation !== locationGeneration) return null;
        currentLocation.value = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          coordinate_system: 'wgs84',
          captured_at: position.timestamp || Date.now(),
        };
        return currentLocation.value;
      } catch (error) {
        if (generation !== locationGeneration) return null;
        const messages = {
          1: '定位权限未开启，请授权定位或在对话中提供出发地',
          2: '暂时无法获取当前位置，请在对话中提供出发地',
          3: '获取当前位置超时，请重试或提供出发地',
        };
        locationError.value = messages[error.code] || '获取当前位置失败，请提供出发地';
        return null;
      } finally {
        if (generation === locationGeneration) isLocating.value = false;
      }
    };

    const refreshLocation = () => acquireCurrentLocation(true);

    const selectAttachments = (event) => {
      const files = Array.from(event.target.files || []);
      selectedAttachments.value.push(...files.slice(0, 8 - selectedAttachments.value.length).map(file => ({
        file, key: `${file.name}-${file.size}-${file.lastModified}`,
      })));
      event.target.value = '';
    };

    const removeSelectedAttachment = (key) => {
      selectedAttachments.value = selectedAttachments.value.filter(item => item.key !== key);
    };

    const deleteAttachment = async (attachmentId) => {
      try {
        const response = await authFetch(`/api/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await readErrorMessage(response, '附件删除失败'));
        chatMessages.value.forEach(message => {
          if (Array.isArray(message.attachments)) {
            message.attachments = message.attachments.filter(item => item.id !== attachmentId);
          }
        });
      } catch (error) {
        loginError.value = error.message || '附件删除失败';
      }
    };

    const uploadSelectedAttachments = async (attachments, signal) => {
      const ids = [];
      for (const item of attachments) {
        signal.throwIfAborted();
        const form = new FormData();
        form.append('file', item.file);
        const response = await authFetch('/api/attachments', { method: 'POST', body: form, signal });
        if (!response.ok) throw new Error(await readErrorMessage(response, '附件上传失败'));
        const data = await readJsonResponse(response);
        ids.push(data.id);
      }
      return ids;
    };
    
    // 当前选中的导航项
    const selectedNavItem = ref('');
    const activeWorkspace = ref('chat');
    const previewArtifactId = ref('');
    const previewReturnWorkspace = ref('files');
    const openFilePreview = (artifactId) => {
      if (!/^[0-9a-f]{32}$/.test(artifactId)) return;
      previewReturnWorkspace.value = activeWorkspace.value === 'chat' ? 'chat' : 'files';
      previewArtifactId.value = artifactId;
      activeWorkspace.value = 'preview';
      selectedNavItem.value = 'files';
      closeMobileSidebar();
    };
    const closeFilePreview = () => {
      activeWorkspace.value = previewReturnWorkspace.value;
      selectedNavItem.value = previewReturnWorkspace.value === 'files' ? 'files' : '';
      previewArtifactId.value = '';
      if (/^#file-preview=[0-9a-f]{32}$/.test(window.location.hash)) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
      }
    };
    const openPreviewFromHash = () => {
      if (!isLoggedIn.value) return;
      const match = /^#file-preview=([0-9a-f]{32})$/.exec(window.location.hash);
      if (match && !(activeWorkspace.value === 'preview' && previewArtifactId.value === match[1])) {
        openFilePreview(match[1]);
      }
    };
    const workspaceTitle = computed(() => {
      if (activeWorkspace.value === 'knowledge') return '知识库';
      if (activeWorkspace.value === 'memory') return '长期记忆';
      if (activeWorkspace.value === 'files') return '生成文件';
      if (activeWorkspace.value === 'preview') return '网页预览';
      if (activeWorkspace.value === 'tools') return '工具与插件';
      return sessions.value.find(session => session.session_id === selectedSessionId.value)?.title
        || chatMessages.value.find(message => message.type === 'user')?.content || '新会话';
    });
    


    // 切换思考过程的折叠状态
    const toggleThinking = (index) => {
      const msg = chatMessages.value[index];
      if (msg && msg.type === 'THINKING') {
        msg.collapsed = !msg.collapsed;
      }
    };
    
    // 暴露给模板
    // return {
    //   toggleThinking,
    //   isLoggedIn,
    //   username,
    //   password,
    //   currentUser,
    

    
    // 处理知识库查询
    const handleKnowledgeBase = () => {
      closeMobileSidebar();
      cancelActiveRequest();
      if (!projectAllowsPlugin('knowledge')) return;
      if (!enabledPlugins.value.includes('knowledge')) enabledPlugins.value = [...enabledPlugins.value, 'knowledge'];
      console.log('打开知识库查询');
      // 清空右侧内容但保持页面结构不变
      processContent.value = null;
      selectedNavItem.value = 'knowledge';
      activeWorkspace.value = 'knowledge';
      // 清除历史会话选中状态
      selectedSessionId.value = '';
    };

    const handleMemory = () => {
      closeMobileSidebar();
      cancelActiveRequest();
      selectedNavItem.value = 'memory';
      activeWorkspace.value = 'memory';
      selectedSessionId.value = '';
    };

    const handleTools = () => {
      closeMobileSidebar();
      selectedNavItem.value = 'tools';
      activeWorkspace.value = 'tools';
      if (!plugins.value.length && !isLoadingPlugins.value) void fetchPlugins(true);
    };
    const returnToChat = () => {
      selectedNavItem.value = '';
      activeWorkspace.value = 'chat';
      nextTick(() => scrollToBottom());
    };

    const handleFiles = () => {
      closeMobileSidebar();
      cancelActiveRequest();
      selectedNavItem.value = 'files';
      activeWorkspace.value = 'files';
      selectedSessionId.value = '';
      sessionTasks.value = [];
      taskError.value = '';
    };
    
    // 处理服务站查询
const handleNetworkSearch = () => {
  closeMobileSidebar();
  cancelActiveRequest();
  if (!projectAllowsPlugin('search')) return;
  if (!enabledPlugins.value.includes('search')) enabledPlugins.value = [...enabledPlugins.value, 'search'];
  selectedNavItem.value = 'network';
  activeWorkspace.value = 'chat';
  selectedSessionId.value = '';
  // 联网搜索功能逻辑可以在这里实现
};

const handleServiceStation = () => {
       closeMobileSidebar();
       cancelActiveRequest();
       const mapPlugin = plugins.value.find(plugin => plugin.id === 'map');
       if (!mapPlugin || !projectAllowsPlugin('map')) return;
       if (!enabledPlugins.value.includes('map')) {
         toggleOptionalPlugin(mapPlugin);
         if (!enabledPlugins.value.includes('map')) return;
       }
      console.log('打开服务站查询');
      // 清空右侧内容但保持页面结构不变
      processContent.value = null;
      selectedNavItem.value = 'service';
      activeWorkspace.value = 'chat';
      // 清除历史会话选中状态
      selectedSessionId.value = '';
    };
    
    // 历史会话相关状态
    const sessions = ref([]);
    const selectedSessionId = ref('');
    const isLoadingSessions = ref(false);
    const showSessions = ref(true); // 控制历史会话的显示/隐藏
    
    // 切换历史会话的显示/隐藏
    const toggleSessions = () => {
      showSessions.value = !showSessions.value;
    };

    // 处理登录
    const handleLogin = async () => {
      const generation = ++authGeneration;
      loginError.value = '';
      try {
        if (isRegistering.value && password.value !== confirmPassword.value) {
          throw new Error('两次输入的密码不一致');
        }
        const response = await fetch(isRegistering.value ? '/api/auth/register' : '/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: username.value.trim(), password: password.value }),
        });
        const data = await readJsonResponse(response);
        if (generation !== authGeneration) return;
        if (!response.ok) {
          const unavailable = response.status === 502 || response.status === 503;
          throw new Error(data.detail || (unavailable ? '后端服务未启动或暂时不可用' : '登录失败'));
        }

        setAuthSession(data.access_token, data.user);
        currentUser.value = data.user.username;
        isLoggedIn.value = true;
        window.scrollTo(0, 0);
        username.value = '';
        password.value = '';
        confirmPassword.value = '';
      } catch (error) {
        if (generation === authGeneration) loginError.value = error.message || '登录失败';
      }
    };

    // 获取历史会话数据
    const fetchUserSessions = async (loadMore = false) => {
      if (!currentUser.value) return;
      if (loadMore && (!nextSessionPage.value || isLoadingSessions.value)) return;
      const generation = authGeneration;
      const requestId = ++sessionListRequestId;
      const selectedGeneration = sessionGeneration;
      const isCurrent = () => generation === authGeneration
        && requestId === sessionListRequestId && selectedGeneration === sessionGeneration;
      
      isLoadingSessions.value = true;
      sessionListError.value = '';
      try {
        const workspaceQuery = selectedProjectId.value && selectedProjectId.value !== 'default' ? `&workspace_id=${encodeURIComponent(selectedProjectId.value)}` : '';
        const response = await authFetch(loadMore ? `/api/user_sessions?page=${nextSessionPage.value}${workspaceQuery}` : `/api/user_sessions${workspaceQuery ? `?${workspaceQuery.slice(1)}` : ''}`);
        
        if (!response.ok) {
          throw new Error(await readErrorMessage(response, '读取历史会话失败'));
        }
        const data = await readJsonResponse(response);
        if (!isCurrent()) return;
        if (data.success && data.sessions) {
          const unread = new Map(sessions.value.map(session => [session.session_id, session.unread_tasks || 0]));
          const incoming = data.sessions.map(session => ({
            ...session,
            unread_tasks: unread.get(session.session_id) || session.unread_tasks || 0,
          }));
          sessions.value = loadMore
            ? [...new Map([...sessions.value, ...incoming].map(session => [session.session_id, session])).values()]
            : incoming;
          nextSessionPage.value = data.next_page || null;
          // 默认选择最新的会话
          if (data.sessions.length > 0 && !selectedSessionId.value) {
            selectSession(data.sessions[0].session_id);
          }
        }
      } catch (error) {
        if (isCurrent()) sessionListError.value = error.message || '读取历史会话失败';
      } finally {
        if (generation === authGeneration && requestId === sessionListRequestId) isLoadingSessions.value = false;
        // 刷新会话列表后：确保最终结果框滚动到底部
        if (isCurrent()) scrollToBottom();
      }
    };

    const fetchSessionTasks = async (sessionId = selectedSessionId.value) => {
      if (!currentUser.value || !sessionId) {
        sessionTasks.value = [];
        taskError.value = '';
        return;
      }
      const generation = authGeneration;
      const selectedGeneration = sessionGeneration;
      isLoadingTasks.value = true;
      taskError.value = '';
      try {
        const response = await authFetch(`/api/sessions/${encodeURIComponent(sessionId)}/tasks`);
        if (!response.ok) throw new Error(await readErrorMessage(response, '读取后台任务失败'));
        const data = await readJsonResponse(response);
        if (generation !== authGeneration || selectedGeneration !== sessionGeneration
          || sessionId !== selectedSessionId.value) return;
        sessionTasks.value = Array.isArray(data.tasks) ? data.tasks : [];
      } catch (error) {
        if (generation === authGeneration && selectedGeneration === sessionGeneration) {
          taskError.value = error.message || '读取后台任务失败';
        }
      } finally {
        if (generation === authGeneration && selectedGeneration === sessionGeneration) {
          isLoadingTasks.value = false;
        }
      }
    };

    const refreshSessionTasks = () => fetchSessionTasks();
    const taskStatusLabel = (status) => ({
      queued: '排队中', running: '执行中', completed: '已完成',
      failed: '执行失败', cancelled: '已取消',
    }[status] || status || '未知状态');
    const taskCanResume = (task) => Boolean(
      task && ['failed', 'cancelled'].includes(task.status) && task.checkpoint,
    );
    const taskCanFollow = (task) => Boolean(task?.run_id);
    const taskActionLabel = (task) => ['queued', 'running'].includes(task?.status) ? '查看进度' : '回放事件';

    const requestDeleteSession = (sessionId) => {
      if (!sessionId || deletingSessionId.value) return;
      pendingDeleteSessionId.value = pendingDeleteSessionId.value === sessionId ? '' : sessionId;
    };

    const cancelDeleteSession = () => {
      if (!deletingSessionId.value) pendingDeleteSessionId.value = '';
    };

    const confirmDeleteSession = async (sessionId) => {
      if (pendingDeleteSessionId.value !== sessionId) return;
      pendingDeleteSessionId.value = '';
      await deleteSession(sessionId);
    };

    const deleteSession = async (sessionId) => {
      if (!sessionId || deletingSessionId.value) return;
      const session = sessions.value.find(item => item.session_id === sessionId);
      const wasSelected = selectedSessionId.value === sessionId;
      const generation = authGeneration;
      deletingSessionId.value = sessionId;
      try {
        const workspaceQuery = selectedProjectId.value && selectedProjectId.value !== 'default' ? `?workspace_id=${encodeURIComponent(selectedProjectId.value)}` : '';
        const response = await authFetch(`/api/sessions/${encodeURIComponent(sessionId)}${workspaceQuery}`, { method: 'DELETE' });
        if (!response.ok) {
          throw new Error(await readErrorMessage(response, '删除会话失败'));
        }
        if (generation !== authGeneration) return;
        sessions.value = sessions.value.filter(item => item.session_id !== sessionId);
        if (wasSelected) {
          cancelActiveRequest();
          sessionGeneration += 1;
          chatMessages.value = [];
          sessionTasks.value = [];
          nextBeforeId.value = null;
          messageHistoryError.value = '';
          selectedSessionId.value = '';
          const nextSession = sessions.value[0];
          if (nextSession) await selectSession(nextSession.session_id);
        }
        if (!sessions.value.length) {
          nextSessionPage.value = null;
        } else if (nextSessionPage.value) {
          // 删除第一页项目后，后续页的 OFFSET 已变化，重新获取第一页避免跳过记录。
          await fetchUserSessions();
        }
      } catch (error) {
        if (generation === authGeneration) sessionListError.value = error.message || '删除会话失败';
      } finally {
        if (generation === authGeneration) deletingSessionId.value = '';
      }
    };


    
    // 新建会话
    const createNewSession = () => {
      activeWorkspace.value = 'chat';
      // 生成新的会话ID (使用时间戳+随机数确保唯一性)
      const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      
      // 创建新会话对象
      const newSession = {
        session_id: newSessionId,
        create_time: new Date().toISOString(),
        memory: [],
        total_messages: 0
      };
      
      // 将新会话添加到会话列表的最前面
      sessions.value.unshift(newSession);
      
      // 清空当前内容
      userInput.value = '';
      
      // 选中新会话
      selectSession(newSessionId);
    };
    
    // 选择会话
    const selectSession = async (sessionId) => {
      closeMobileSidebar();
      detachActiveRequest();
      sessionGeneration += 1;
      activeWorkspace.value = 'chat';
      selectedSessionId.value = sessionId;
      // 清除导航项选中状态
      selectedNavItem.value = '';
      sessionTasks.value = [];
      taskError.value = '';
      void fetchSessionTasks(sessionId);
      // 找到选中的会话
      const session = sessions.value.find(s => s.session_id === sessionId);
      if (session) session.unread_tasks = 0;
      
      // 清空当前内容
      chatMessages.value = [];
      nextBeforeId.value = null;
      isLoadingMessages.value = false;
      messageHistoryError.value = '';

      if (session && !Array.isArray(session.memory)) {
        await loadMessagePage();
        return;
      }
      
      if (session && session.memory && Array.isArray(session.memory) && session.memory.length > 0) {
        let lastType = null;
        
        session.memory.forEach(msg => {
          if (!msg || (!msg.content && !msg.attachments?.length)) return;
          
          // 映射角色类型
          let type = msg.role;
          if (type === 'process') type = 'THINKING';
          
          // 合并连续的思考过程
          if (type === 'THINKING' && lastType === 'THINKING') {
            const lastMsg = chatMessages.value[chatMessages.value.length - 1];
            lastMsg.content += '\n' + msg.content;
          } else {
            chatMessages.value.push({
              type: type, // 'user', 'assistant', 'THINKING'
              content: msg.content || '',
              attachments: msg.attachments || [],
              sources: normalizeSources(msg.sources),
            });
          }
          lastType = type;
        });
        
        // 滚动到底部
        nextTick(() => {
          scrollToBottom();
        });
      }
    };

    const loadMessagePage = async (older = false) => {
      if (isLoadingMessages.value || isProcessing.value) return;
      const generation = sessionGeneration;
      const authentication = authGeneration;
      const sessionId = selectedSessionId.value;
      if (!sessionId) return;
      const requestId = nextRequestId;
      const isCurrent = () => generation === sessionGeneration && authentication === authGeneration
        && requestId === nextRequestId && sessionId === selectedSessionId.value;
      isLoadingMessages.value = true;
      messageHistoryError.value = '';
      const container = processContent.value;
      const oldHeight = container?.scrollHeight || 0;
      const oldTop = container?.scrollTop || 0;
      try {
        const cursor = older && nextBeforeId.value ? `?before_id=${nextBeforeId.value}` : '';
        const workspaceQuery = selectedProjectId.value && selectedProjectId.value !== 'default' ? `${cursor ? '&' : '?'}workspace_id=${encodeURIComponent(selectedProjectId.value)}` : '';
        const response = await authFetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages${cursor}${workspaceQuery}`);
        if (!response.ok) throw new Error(await readErrorMessage(response, '读取消息失败'));
        const data = await readJsonResponse(response);
        if (!isCurrent()) return;
        const messages = (data.messages || []).filter(message => message.role !== 'system').map(message => ({
          id: message.id, type: message.role === 'process' ? 'THINKING' : message.role,
          content: message.content || '', attachments: message.attachments || [], sources: normalizeSources(message.sources),
        }));
        const existing = new Set(chatMessages.value.map(message => message.id).filter(Boolean));
        chatMessages.value = older ? [...messages.filter(message => !existing.has(message.id)), ...chatMessages.value] : messages;
        nextBeforeId.value = data.next_before_id || null;
        await nextTick();
        if (!isCurrent()) return;
        if (older && container) container.scrollTop = oldTop + container.scrollHeight - oldHeight;
        else scrollToBottom();
      } catch (error) {
        if (isCurrent()) messageHistoryError.value = error.message || '读取消息失败';
      } finally {
        if (isCurrent()) isLoadingMessages.value = false;
      }
    };
    const loadOlderMessages = () => nextBeforeId.value ? loadMessagePage(true) : Promise.resolve();

    const isActiveRequest = (request) => activeRequest?.id === request.id
      && selectedSessionId.value === request.sessionId
      && selectedProjectId.value === request.projectId
      && authGeneration === request.authGeneration;

    const waitBeforeTaskReconnect = (attempt) => new Promise(resolve => {
      window.setTimeout(resolve, Math.min(2000, 400 * (attempt + 1)));
    });

    const consumeSSEResponse = async (request, response) => {
      if (!response.ok) throw new Error(await readErrorMessage(response, '读取任务事件失败'));
      if (!response.body) throw new Error('服务没有返回事件流');
      request.reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await request.reader.read();
        if (!isActiveRequest(request)) return false;
        if (done) {
          buffer += decoder.decode();
          if (buffer.trim()) processSSEData(buffer);
          return request.finished;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        for (let index = 0; index < lines.length - 1; index += 1) {
          if (lines[index].trim()) processSSEData(lines[index]);
        }
        buffer = lines[lines.length - 1];
      }
    };

    const subscribeToTaskEvents = async (request) => {
      let attempt = 0;
      while (isActiveRequest(request) && !request.finished && attempt < 4) {
        try {
          const response = await authFetch(`/api/tasks/${encodeURIComponent(request.taskRunId)}/events`, {
            signal: request.controller.signal,
          });
          const finished = await consumeSSEResponse(request, response);
          if (finished || !isActiveRequest(request)) return Boolean(finished);
          const statusResponse = await authFetch(`/api/tasks/${encodeURIComponent(request.taskRunId)}`, {
            signal: request.controller.signal,
          });
          if (statusResponse.ok) {
            const status = await readJsonResponse(statusResponse);
            if (['completed', 'failed', 'cancelled'].includes(status.status)) {
              request.finished = true;
              if (status.status !== 'completed' && status.error) {
                request.taskFailure = status.error;
              }
              return true;
            }
          }
        } catch (error) {
          if (error.name === 'AbortError' || !isActiveRequest(request)) throw error;
        }
        if (!isActiveRequest(request)) return false;
        attempt += 1;
        await waitBeforeTaskReconnect(attempt);
      }
      return request.finished;
    };

    const followTask = async (task) => {
      if (!taskCanFollow(task) || isProcessing.value || !selectedSessionId.value) return;
      cancelActiveRequest();
      const request = {
        id: ++nextRequestId,
        sessionId: selectedSessionId.value,
        projectId: selectedProjectId.value,
        authGeneration,
        controller: new AbortController(),
        reader: null,
        taskRunId: task.run_id,
        planId: null,
        sources: [],
        seenEventIds: new Set(),
        finished: false,
        taskFailure: '',
        replayMode: true,
        cancelTaskOnStop: ['queued', 'running'].includes(task.status),
        reloadArchiveOnFinish: ['queued', 'running'].includes(task.status),
        detached: false,
      };
      activeRequest = request;
      isProcessing.value = true;
      try {
        const finished = await subscribeToTaskEvents(request);
        if (!finished && isActiveRequest(request)) {
          throw new Error('任务事件流意外结束，已重试多次');
        }
      } catch (error) {
        if (isActiveRequest(request) && error.name !== 'AbortError') {
          taskError.value = error.message || '读取任务事件失败';
          appendVisibleError(taskError.value);
        }
      } finally {
        if (isActiveRequest(request)) {
          interruptPlan(request);
          if (request.taskFailure) {
            taskError.value = request.taskFailure;
            appendVisibleError(request.taskFailure);
          }
          isProcessing.value = false;
          activeRequest = null;
          await fetchSessionTasks(request.sessionId);
          await fetchUserSessions();
          if (request.reloadArchiveOnFinish && selectedSessionId.value === request.sessionId && !isLoadingMessages.value) {
            const taskPlans = chatMessages.value
              .filter(message => message.type === 'PLAN' && message.plan?.run_id === request.taskRunId);
            await loadMessagePage();
            if (taskPlans.length && selectedSessionId.value === request.sessionId) {
              const firstAssistant = chatMessages.value.findIndex(message => message.type === 'assistant');
              const insertAt = firstAssistant < 0 ? chatMessages.value.length : firstAssistant;
              chatMessages.value.splice(insertAt, 0, ...taskPlans);
            }
          }
          scrollToBottom();
        }
      }
    };

    const resumeTask = async (task) => {
      if (!taskCanResume(task) || resumingTaskId.value) return;
      resumingTaskId.value = task.run_id;
      taskError.value = '';
      try {
        const response = await authFetch(`/api/tasks/${encodeURIComponent(task.run_id)}/resume`, { method: 'POST' });
        if (!response.ok) throw new Error(await readErrorMessage(response, '恢复任务失败'));
        const resumed = await readJsonResponse(response);
        await fetchSessionTasks(task.session_id);
        if (taskCanFollow(resumed)) await followTask(resumed);
      } catch (error) {
        taskError.value = error.message || '恢复任务失败';
      } finally {
        resumingTaskId.value = '';
      }
    };
    
    // 处理登出
    const handleLogout = () => {
      resetAuthState();
    };
    
    // 跳转到登录页面
    const goToLogin = () => {
      resetAuthState();
    };
    
    // 处理发送请求
      const handleSend = async (event) => {
        // 阻止回车键的默认行为（插入换行）
        if (event) {
          event.preventDefault();
        }
        if (!userInput.value.trim() || isLoadingMessages.value) return;
        const queryText = userInput.value.trim();
        
        // 立即强制滚动到页面顶部，防止页面下移
        window.scrollTo(0, 0);
        
        // 检查登录状态，只有点击发送时才检查
        if (!getAuthToken()) {
          // 如果没有登录凭证，跳转到登录页面
          resetAuthState();
          return;
        }
        cancelActiveRequest();
        if (!selectedSessionId.value) createNewSession();
        const projectId = selectedProjectId.value;
        const pluginSelection = requestPluginSelection();
        const request = {
          id: ++nextRequestId,
          sessionId: selectedSessionId.value,
          projectId,
          authGeneration,
          controller: new AbortController(),
          reader: null,
          taskRunId: null,
          cancelTaskOnStop: true,
          seenEventIds: new Set(),
          finished: false,
          taskFailure: '',
          replayMode: false,
          sources: [],
        };
        activeRequest = request;
        const isCurrent = () => activeRequest?.id === request.id
          && selectedSessionId.value === request.sessionId
          && selectedProjectId.value === request.projectId
          && authGeneration === request.authGeneration;
        const attachments = [...selectedAttachments.value];
        const modelProfileId = selectedModelProfile.value || null;
        const temporaryModel = modelProfileId ? null : activeTemporaryModel.value;
        const requestPlugins = [...pluginSelection.enabled];
        const requestConfirmedPlugins = [...pluginSelection.confirmed];
        isProcessing.value = true;
        try {
        const origin = queryNeedsDeviceLocation(queryText)
          ? await acquireCurrentLocation()
          : null;
        if (!isCurrent()) return;
        
        // 自动收起之前的思考过程
        chatMessages.value.forEach(msg => {
          if (msg.type === 'THINKING') {
            msg.collapsed = true;
          }
        });
        
        // 将会话显示逻辑与历史会话保持一致：添加用户消息
        chatMessages.value.push({
          type: 'user',
          content: queryText,
          attachments: attachments.map(item => ({ id: item.key, name: item.file.name }))
        });
        
        // 请求发起时：添加用户消息后立即滚动到结果框底部
        scrollToBottom();
        
        // 准备请求数据，包含用户ID和选中的会话ID
        const attachmentIds = attachments.length
          ? await uploadSelectedAttachments(attachments, request.controller.signal) : [];
        if (!isCurrent()) return;
        const requestData = {
          query: queryText,
          context: {
            session_id: request.sessionId
          },
          origin,
          model_profile_id: modelProfileId,
          enabled_plugins: requestPlugins,
          confirmed_plugins: requestConfirmedPlugins,
          project_id: request.projectId,
          work_mode: workMode.value,
          attachment_ids: attachmentIds,
          temporary_model: temporaryModel,
        };
        

        
        console.log('发送请求，会话ID:', selectedSessionId.value);
        
          // 调用后端API
          const response = await authFetch('/api/query', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData),
            signal: request.controller.signal
          });
          if (!isCurrent()) {
            void response.body?.cancel().catch(() => {});
            return;
          }
          
          if (!response.ok) {
            throw new Error(await readErrorMessage(response, '发送请求失败'));
          }
          
        let streamFinished = false;
        try {
          streamFinished = await consumeSSEResponse(request, response);
        } catch (error) {
          if (error.name === 'AbortError') throw error;
          if (!request.taskRunId) throw error;
        }
        if (!isCurrent()) return;
        if (!streamFinished) {
          if (!request.taskRunId) throw new Error('事件连接中断，且没有取得任务编号，无法恢复订阅');
          const recovered = await subscribeToTaskEvents(request);
          if (!recovered && isCurrent()) throw new Error('任务事件连接中断，自动重连后仍未恢复');
        }
          
        } catch (error) {
          if (isCurrent() && error.name !== 'AbortError') {
            const detail = error.message || '服务暂时不可用，请稍后重试';
            const errorMsg = detail.startsWith('请求失败') ? detail : `请求失败：${detail}`;
            appendVisibleError(errorMsg);
            console.error('Error:', error);
          }
        } finally {
          if (isCurrent()) {
          interruptPlan(request);
          if (request.taskFailure && !chatMessages.value.at(-1)?.content?.includes(request.taskFailure)) {
            appendVisibleError(request.taskFailure);
          }
          isProcessing.value = false;
          activeRequest = null;
          
          // 请求结束时：确保最终结果框滚动到底部
          scrollToBottom();

          // 请求结束后，不自动收起思考过程，保持展开状态以便用户查看
          // const lastMsg = chatMessages.value[chatMessages.value.length - 1];
          // for (let i = chatMessages.value.length - 1; i >= 0; i--) {
          //    if (chatMessages.value[i].type === 'THINKING') {
          //      chatMessages.value[i].collapsed = true;
          //      break; 
          //    }
          // }
          
          // 会话请求结束后刷新历史会话区域
          fetchUserSessions();
          void fetchSessionTasks(request.sessionId);
          userInput.value = '';
          selectedAttachments.value = [];
          activeTemporaryModel.value = null;
          } else if (request.detached) {
            const backgroundSession = sessions.value.find(s => s.session_id === request.sessionId);
            if (backgroundSession) backgroundSession.unread_tasks = (backgroundSession.unread_tasks || 0) + 1;
            // 刷新会话元数据，确保切回会话时能看到已完成的回答。
            fetchUserSessions();
          }
        }
      };
      
      // 处理SSE格式的数据
    const processSSEData = (data) => {
        const parsedData = parseSSELine(data);
        if (parsedData) {
              const eventId = parsedData.id;
              if (eventId && activeRequest?.seenEventIds?.has(eventId)) return;
              if (eventId && activeRequest?.seenEventIds) activeRequest.seenEventIds.add(eventId);
              if (parsedData.task?.run_id && activeRequest) {
                activeRequest.taskRunId = parsedData.task.run_id;
                return;
              }
              const eventMetadata = parsedData.metadata || {};
              const metadataParts = [];
              if (eventMetadata.agentName) metadataParts.push(`Agent ${eventMetadata.agentName}`);
              if (eventMetadata.toolName) metadataParts.push(`工具 ${eventMetadata.toolName}`);
              if (metadataParts.length) streamTextToProcess(`运行轨迹：${metadataParts.join(' · ')}\n`);
              if (parsedData.content?.contentType === 'sagegpt/plan') {
                const plan = parsedData.content;
                if (!activeRequest || typeof plan.run_id !== 'string' || !Array.isArray(plan.steps)) return;
                activeRequest.planId = plan.run_id;
                const message = chatMessages.value.find(m => m.type === 'PLAN' && m.plan.run_id === plan.run_id);
                if (message) message.plan = plan;
                else chatMessages.value.push({ type: 'PLAN', content: '', plan });
                scrollToBottom();
                return;
              }
              if (parsedData.content?.contentType === 'sagegpt/sources') {
                if (activeRequest) activeRequest.sources = normalizeSources(parsedData.content.sources);
                return;
              }
              if (parsedData.content?.contentType === 'sagegpt/grounding-trace') {
                const trace = parsedData.content;
                const phases = {
                  planning: '查询范围', retrieval: '资料检索', review: '证据审查', workflow: '资料流程',
                };
                const states = {
                  started: '开始', completed: '完成', sufficient: '通过', insufficient: '资料不足',
                  conflicting: '发现冲突', unverified: '核验未通过', failed: '失败',
                };
                const origins = { knowledge: '知识库', web: '网页', attachment: '附件' };
                const phase = phases[trace.phase] || '资料流程';
                const status = states[trace.status] || trace.status || '更新';
                const origin = origins[trace.origin] ? `（${origins[trace.origin]}）` : '';
                streamTextToProcess(`${phase}${origin}：${status}${trace.detail ? `，${trace.detail}` : ''}\n`);
                return;
              }

              let kind; // 变量名改为 kind
              let text;

              // -----------------------------------------------------------
              // 适配新的 StreamPacket 结构
              // 结构: { content: { kind: "...", text: "...", ... }, ... }
              // -----------------------------------------------------------
              if (parsedData.content && typeof parsedData.content === 'object') {
                // 1. 获取文本内容
                text = parsedData.content.text;

                // 2. 获取内容分类 (kind)
                if (parsedData.content.kind) {
                  // 新版后端字段名为 kind
                  kind = parsedData.content.kind;
                } else if (parsedData.content.type) {
                  // 兼容旧版字段名 type
                  kind = parsedData.content.type;
                }

                // 3. 处理结束信号 (如果内容是 FinishMessageBody)
                if (parsedData.status === 'FINISHED' || parsedData.content.contentType === 'sagegpt/finish') {
                   if (activeRequest) activeRequest.finished = true;
                   if (
                     parsedData.metadata?.finishReason === 'ERROR'
                     && parsedData.metadata?.errorMessage
                   ) {
                     if (activeRequest) activeRequest.taskFailure = parsedData.metadata.errorMessage;
                     else appendVisibleError(parsedData.metadata.errorMessage);
                   }
                   return;
                }
              }

              // -----------------------------------------------------------
              // 降级兼容旧逻辑 (防止后端回滚导致前端挂掉)
              // -----------------------------------------------------------
              else if (parsedData.type && parsedData.content) {
                kind = parsedData.type;
                text = parsedData.content;
              }

              // -----------------------------------------------------------
              // 根据 kind 分发处理逻辑
              // -----------------------------------------------------------
              if (kind && text) {
                // console.log('Processing kind:', kind, 'text:', text); // 调试日志

                switch (kind) {
                  case 'ANSWER':
                    if (!activeRequest?.replayMode) streamTextToAnswer(text);
                    break;

                  case 'THINKING':
                    streamTextToProcess(text);
                    break;

                  case 'PROCESS':
                    streamTextToProcess(text + '\n');
                    scrollToBottom();
                    break;

                  default:
                    console.log('Unknown content kind:', kind);
                    // 默认作为 PROCESS 处理
                    streamTextToProcess(text + '\n');
                }
              }
        }
    };
      
      // 处理取消请求
      const handleCancel = () => {
        cancelActiveRequest();
        streamTextToProcess('请求已取消\n');
      };

    // 移除未使用的handleStreamingResponse函数

    // 流式更新答案文本（使用Markdown渲染）
    const streamTextToAnswer = (text) => {
      const lastMsg = chatMessages.value[chatMessages.value.length - 1];
      
      // 更新统一的聊天记录
      // const lastMsg = chatMessages.value[chatMessages.value.length - 1]; // 已在函数开头声明
      if (lastMsg && lastMsg.type === 'assistant') {
        lastMsg.content += text;
      } else {
        chatMessages.value.push({ type: 'assistant', content: text, sources: activeRequest?.sources || [] });
      }
      chatMessages.value = [...chatMessages.value]; // Trigger reactivity
      
      // 后端返回数据时：确保最终结果框滚动到底部
      scrollToBottom();
    };

    const appendVisibleError = (text) => {
      chatMessages.value.push({ type: 'error', content: text });
      chatMessages.value = [...chatMessages.value];
      scrollToBottom();
    };
    
    // 流式更新处理消息
    const streamTextToProcess = (text) => {
      // 更新统一的聊天记录
      const lastMsg = chatMessages.value[chatMessages.value.length - 1];
      if (lastMsg && lastMsg.type === 'THINKING') {
        lastMsg.content += text;
        // 如果是新消息且正在处理中，确保展开
        if (isProcessing.value && lastMsg.collapsed === undefined) {
           // 使用 reactive 属性，初始化为 false (展开)
           lastMsg.collapsed = false;
        }
      } else {
        chatMessages.value.push({ 
          type: 'THINKING', 
          content: text,
          collapsed: false // 默认为展开状态
        });
      }
      chatMessages.value = [...chatMessages.value];
      
      scrollToBottom();
    };
    
    // 滚动到底部
    const scrollToBottom = () => {
      setTimeout(() => {
        // 滚动新的消息容器
        const chatContainer = document.querySelector('.chat-message-container');
        if (chatContainer) {
          chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        // 确保页面不整体滚动，无条件强制滚动到顶部
        window.scrollTo(0, 0);
      }, 0);
    };

    // 监听登录状态变化，登录成功后获取会话列表
    watch(isLoggedIn, (newVal) => {
      if (newVal && currentUser.value) {
        fetchUserSessions();
        fetchModelProfiles();
        fetchPlugins();
        fetchProjects();
        openPreviewFromHash();
      }
    });
    watch(selectedProjectId, async (workspaceId, previousId) => {
      if (!isLoggedIn.value || workspaceId === previousId) return;
      cancelActiveRequest();
      workspaceDeleteError.value = '';
      // 工具启用确认只属于当前工作区，切换后从安全的默认能力重新开始。
      confirmedPlugins.value = [];
      enabledPlugins.value = defaultPluginsForProject(currentProject());
      reconcileProjectPlugins();
      selectedNavItem.value = '';
      selectedSessionId.value = '';
      chatMessages.value = [];
      await fetchUserSessions();
    });
    
    // 组件挂载时检查登录状态并获取会话列表
    onMounted(() => {
      if (isLoggedIn.value && currentUser.value) {
        fetchUserSessions();

        // 组件挂载默认加载时：确保最终结果框滚动到底部
        nextTick(() => {
          scrollToBottom();
        });
      }
      
      // 添加键盘快捷键监听器
      document.addEventListener('keydown', handleKeyDown);
      window.addEventListener('resize', updateViewport);
      window.addEventListener('hashchange', openPreviewFromHash);
      openPreviewFromHash();
    });
    
    onUnmounted(() => {
      // 移除键盘快捷键监听器
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', updateViewport);
      window.removeEventListener('hashchange', openPreviewFromHash);
      authGeneration += 1;
      locationGeneration += 1;
      cancelActiveRequest();
    });
    
    // 处理键盘快捷键
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') closeMobileSidebar();
      // Ctrl+K 快捷键新建会话
      if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        createNewSession();
      }
    };
    
    // 切换侧边栏展开/收起状态
    const toggleSidebar = () => {
      isSidebarExpanded.value = !isSidebarExpanded.value;
      console.log('侧边栏状态:', isSidebarExpanded.value ? '展开' : '收起');
    };
    
    return {
      // 登录相关状态
      isLoggedIn,
      username,
      password,
      confirmPassword,
      isRegistering,
      toggleRegisterMode,
      currentUser,
      loginError,
      showUserInfo,
      toggleUserInfo,
      avatarContainerRef,
      handleLogin,
      handleLogout,
      goToLogin,
      // 主界面相关
      userInput,
      chatMessages,
      processContent,
      isProcessing,
      isLocating,
      currentLocation,
      modelProfiles,
      selectedModelProfile,
      showModelConfig, customModel, customModelMode, modelConfigMessage, applyCustomModel, deleteCurrentModelProfile,
      selectedAttachments, attachmentInputRef, selectAttachments, removeSelectedAttachment, deleteAttachment,
      plugins,
      projects, createWorkspace,
      deleteCurrentWorkspace,
      showWorkspaceCreate, workspaceName, workspaceCreateError, workspaceDeleteError, deletingWorkspaceId,
      selectedProjectId,
      projectAllowsPlugin,
      workMode, workModes,
      enabledPlugins,
      confirmedPlugins,
      toggleOptionalPlugin,
      toggleCorePlugin,
      pluginDescription,
      pluginWorkspace, isLoadingPlugins, pluginLoadError, fetchPlugins, handleTools, returnToChat,
      locationButtonTitle,
      refreshLocation,
      handleSend,
      handleCancel,
      renderMarkdown,
      // 历史会话相关
      sessions,
      selectedSessionId,
      deletingSessionId,
      pendingDeleteSessionId,
      isLoadingSessions,
      nextSessionPage, nextBeforeId, isLoadingMessages, messageHistoryError, sessionListError,
      loadOlderMessages, loadMessagePage,
      sessionTasks, isLoadingTasks, taskError, resumingTaskId,
      refreshSessionTasks, taskStatusLabel, taskCanFollow, taskActionLabel, taskCanResume,
      followTask, resumeTask,
      showSessions,
      toggleSessions,
      // 导航栏相关
      selectedNavItem,
      activeWorkspace,
      workspaceTitle,
      handleKnowledgeBase,
      handleMemory,
      handleFiles,
      previewArtifactId, openFilePreview, closeFilePreview,
  handleNetworkSearch,
  handleServiceStation,
      selectSession,
      fetchUserSessions,
      requestDeleteSession,
      confirmDeleteSession,
      cancelDeleteSession,
      deleteSession,
      createNewSession,

      // 侧边栏相关
      isSidebarExpanded,
      isMobile,
      mobileSidebarToggle,
      closeMobileSidebar,
      toggleSidebar,
      // 思考过程相关
      toggleThinking
    };
  }
};
</script>

<style scoped>
.manage-tools-link { display: inline-flex; align-items: center; gap: 5px; margin-top: 12px; padding: 6px 9px; border: 1px solid #d5dfdb; border-radius: 6px; color: #147565; background: #fff; font-size: 12px; cursor: pointer; }
.tools-toggle.selected { color: #147565; background: #e6f2ef; }
.tools-entry-count { display: grid; place-items: center; min-width: 22px; height: 22px; padding: 0 4px; border-radius: 6px; background: #e6f2ef; color: #147565; font-size: 11px; }
/* 思考过程头部样式 */
.thinking-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  transition: color 0.2s;
}

.thinking-header:hover {
  color: var(--tech-text-main);
}

.thinking-text {
  font-weight: 500;
}

.thinking-icon {
  transition: transform 0.3s ease;
  opacity: 0.7;
}

.thinking-icon.collapsed {
  transform: rotate(-90deg);
}

.app-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 5px;
  padding-bottom: 10px; /* 减小下边距 */
  box-sizing: border-box;
  min-height: 100vh;
  overflow: hidden; /* 防止页面整体滚动 */
}

/* 主内容区域布局 */
.main-content {
  display: flex;
  flex: 1;
  gap: 20px;
  overflow: hidden;
}

/* 左侧历史会话列表样式 */
.sessions-sidebar {
  width: 300px;
  background-color: #fff;
  border: 1px solid #ccc;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.sidebar-header {
  padding: 15px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.refresh-button {
  padding: 6px 12px;
  background-color: #2196F3;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.refresh-button:hover:not(:disabled) {
  background-color: #1976D2;
}

.refresh-button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.sessions-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}



/* 登录页面样式 */
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  flex: 1;
  padding: 20px;
}

.login-form {
  background: white;
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
  text-align: center;
}

.login-logo {
  margin: 0 auto 20px;
}

.login-title {
  margin: 0 0 30px;
  font-size: 28px;
  font-weight: 700;
  color: #333;
  background: linear-gradient(90deg, #4CAF50, #2196F3);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-input-group {
  margin-bottom: 20px;
  text-align: left;
}

.login-input-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #555;
}

.login-input-group input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 16px;
  transition: border-color 0.3s ease;
  box-sizing: border-box;
}

.login-input-group input:focus {
  outline: none;
  border-color: #2196F3;
  box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
}

.login-error {
  color: #f44336;
  margin-bottom: 20px;
  padding: 10px;
  background-color: #ffebee;
  border-radius: 4px;
}

.login-button {
    width: 100%;
    padding: 14px;
    background-color: #2196F3;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .login-button:hover {
    background-color: #1976D2;
  }

.login-hint {
  margin-top: 20px;
  padding: 15px;
  background-color: #f5f5f5;
  border-radius: 6px;
  font-size: 14px;
  color: #666;
}

.login-hint p {
  margin: 5px 0;
}

/* 用户信息和登出按钮 */
.user-info {
  display: flex;
  align-items: center;
  gap: 15px;
}

.current-user {
  font-size: 14px;
  color: #666;
  font-weight: 500;
  white-space: nowrap;
}

.logout-button {
  padding: 8px 10.67px;
  background-color: #f44336;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.logout-button:hover {
  background-color: #d32f2f;
}

/* 顶部标题区域 */
.app-header {
  background-color: white;
  border-radius: 8px;
  padding: 10px 15px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.app-branding {
  display: flex;
  align-items: center;
  gap: 15px;
}

/* 扁平风格Logo */
.its-logo-flat {
  display: flex;
  align-items: center;
  justify-content: center;
}

.its-logo-flat svg {
  filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.1));
}

/* 扁平风格标题 */
.its-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 1px;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  text-transform: uppercase;
  /* 蓝色渐变效果 */
  background: linear-gradient(90deg, #2196F3, #90CAF9);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-fill-color: transparent;
}

.display-container {
  display: flex;
  flex: 1;
  overflow: hidden;
  margin-top: 5px;
  margin-bottom: 5px;
  min-height: 500px; /* 设置最小高度确保有足够空间显示 */
}

.result-container {
  flex: 1;
  padding: 15px;
  display: flex;
  flex-direction: column;
  /* background-color: #f5f5f5; */
  overflow: visible;
  height: auto;
  box-sizing: border-box;
  border-radius: 8px;
  border: 1px solid #fff; /* 添加默认边框 */
}

/* 程序处理中时的渐变闪烁动画 */
.result-container.processing {
  animation: gradient-pulse 1.5s infinite ease-in-out;
}

@keyframes gradient-pulse {
  0% {
    border-color: #fff;
  }
  50% {
    border-color: #2196F3; /* 蓝色边框 */
  }
  100% {
    border-color: #fff;
  }
}


/* 中间流程框样式 */
.process-container {
  width: 100%;
  max-height: 30%; /* 限制最大高度 */
  min-height: 100px;
  margin: 0 0 15px 0; /* 正常的下边距 */
  padding: 10px;
  background-color: #f8f9fa; 
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.process-container h3,
.result-container h3 {
  margin: 0 0 10px 0;
  color: #333;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

/* 确保标题前有小图标提示 */
.process-container h3::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background-color: #2196F3;
  margin-right: 8px;
  border-radius: 2px;
}

.process-content {
    flex: 1;
    overflow-y: auto;
    padding: 5px;
    background-color: white;
    border-radius: 4px;
    font-size: 13px;
    border: 1px solid #eee;
  }

.result-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 10px 10px; /* 将上边距减小到0 */
  background-color: white;
  border-radius: 4px;
  white-space: pre-wrap;
  text-align: left;
  font-size: 14px;
  margin-top: 0; /* 确保上边距为0 */
}

.message-item {
    margin-bottom: 8px;
    padding: 5px;
    border-radius: 4px;
    text-align: left;
    line-height: 1.5;
    word-wrap: break-word;
    font-size: 16px !important;
  }

  /* 添加markdown样式 */
  .markdown {
    font-size: 16px !important;
    line-height: 1.6 !important;
  }

  .markdown .paragraph {
    margin-bottom: 16px !important;
    font-size: 16px !important;
    line-height: 1.8 !important;
    color: #333 !important;
  }
  
  /* 确保结果内容中的文本样式 */
  .result-content {
    font-size: 16px !important;
  }
  
  /* 确保段落样式 */
  .result-content p {
    font-size: 16px !important;
    line-height: 1.8 !important;
    margin-bottom: 1px !important;
    margin-top: 1px !important;
    color: #333 !important;
    display: inline-block !important;
  }
  
  /* 添加更多样式以确保匹配用户要求的格式 */
  .result-content > div {
    font-size: 16px !important;
    line-height: 1.8 !important;
  }
  
  /* 确保所有文本元素的样式 */
  .result-content * {
    font-size: 16px !important;
    line-height: 1.8 !important;
    color: #333 !important;
  }
  
  /* 使用深度选择器确保样式穿透组件边界 */
  :deep(.result-content) {
    font-size: 16px !important;
  }
  
  :deep(.result-content) * {
    font-size: 16px !important;
    line-height: 1.8 !important;
    color: #333 !important;
  }
  
  /* 确保段落样式 */
  :deep(.result-content p) {
    font-size: 16px !important;
    line-height: 1.8 !important;
    margin-bottom: 1px !important;
    margin-top: 1px !important;
    color: #333 !important;
    display: inline-block !important;
  }

  /* 用户消息样式 - 右对齐、宽度限制（不超过三分之二）、背景色 */
  /* 在结果框中为用户消息添加样式 */
  :deep(.result-content) {
    position: relative;
  }
  
  :deep(.result-content) [v-pre] {
    white-space: pre-wrap;
    word-break: break-word;
  }
  
  /* 使用CSS伪元素和属性选择器处理标记的用户消息 */
  :deep(.result-content) [v-pre] {
    line-height: 1.6;
  }
  
  /* 用户消息样式 - 使用正则匹配[USER]标记的消息 */
  :deep(.result-content) [v-pre] {
    /* 基础样式 */
    font-size: 14px;
  }
  
  /* 为最终结果框中的用户消息和助手消息添加样式 */
  :deep(.result-content) .user-message {
    background-color: #f5f5f5; /* 浅灰色背景 */
    color: #1565c0;
    display: inline-block; /* 使元素宽度适应内容 */
    text-align: left; /* 默认左对齐 */
    margin-left: auto;
    margin-right: 0;
    max-width: 66.6%; /* 不超过容器的三分之二 */
    border-radius: 8px;
    padding: 10px 15px;
    margin-bottom: 8px;
    word-break: break-word;
    line-height: 1.6;
    white-space: pre-wrap;
  }
  
  /* 使用伪元素技巧实现单行右对齐，多行左对齐 */
  :deep(.result-content) .user-message {
    text-align: left;
  }

  /* 让整个消息块右对齐 */
  :deep(.result-content) {
    text-align: left;
  }
  
  /* 确保助手消息仍然左对齐 */
  :deep(.result-content) .assistant-message {
    text-align: left;
    display: block;
  }
  
  :deep(.result-content) .assistant-message {
    background-color: #ffffff; /* 白色背景 */
    color: #333;
    text-align: left;
    margin-left: 0;
    margin-right: auto;
    max-width: 100%;
    padding: 10px 15px;
    margin-bottom: 8px;
    word-break: break-word;
    line-height: 1.6;
  }
  
  /* 保留.message-item.user样式，以备后续可能的其他用途 */
  .message-item.user {
    background-color: #e3f2fd;
    color: #1565c0;
    text-align: right;
    margin-left: auto;
    max-width: 66.6%; /* 不超过容器的三分之二 */
    border-radius: 8px;
    padding: 10px;
  }

  .message-item.THINKING {
    background-color: #f0f7ff;
    color: #0066cc;
    white-space: pre-wrap; /* 保留空格和换行，但长行依然换行 */
    word-break: break-all; /* 确保超长单词能被截断 */
  }

  .message-item.PROCESS {
    background-color: #f0f7ff;
    color: #0066cc;
    /*background-color: #fff9f0;
    color: #cc6600;
    font-weight: bold; */
  }

  /* Markdown 样式 */
  :deep(h1) {
    font-size: 24px;
    margin: 16px 0 8px;
    color: #333;
  }

  :deep(h2) {
    font-size: 20px;
    margin: 14px 0 7px;
    color: #444;
  }

  :deep(h3) {
    font-size: 18px;
    margin: 12px 0 6px;
    color: #555;
  }

  :deep(p) {
    margin: 8px 0;
    line-height: 1.6;
  }

  :deep(ul), :deep(ol) {
    margin: 8px 0;
    padding-left: 24px;
  }

  :deep(li) {
    margin: 4px 0;
  }

  :deep(pre) {
    background-color: #f5f5f5;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: 'Courier New', monospace;
  }

  :deep(code) {
    background-color: #f5f5f5;
    padding: 2px 4px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
  }

  :deep(strong) {
    font-weight: bold;
  }

  :deep(em) {
    font-style: italic;
  }

  :deep(a) {
    color: #2196f3;
    text-decoration: none;
  }

  :deep(a:hover) {
    text-decoration: underline;
  }

.input-container {
  padding: 0;
  margin-top: auto;
}

.textarea-with-button {
  position: relative;
  display: inline-block;
  width: 100%;
  max-width: 50vw;
}

.textarea-with-button textarea {
  width: 100%;
  padding: 12px 88px 12px 12px;
  border: 1px solid #ccc;
  border-radius: 12px;
  resize: none;
  height: 100px;
  font-size: 16px;
  font-family: inherit;
}

.textarea-with-button .location-button {
  position: absolute;
  right: 52px;
  bottom: 12px;
  width: 32px;
  height: 32px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
  color: #64748b;
}

.textarea-with-button .location-button:hover {
  background: #f1f5f9;
  color: #0f766e;
}

.textarea-with-button .location-button.active {
  border-color: #0f766e;
  background: #ecfdf5;
  color: #0f766e;
}

.textarea-with-button .location-button.locating svg {
  animation: location-spin 1s linear infinite;
}

@keyframes location-spin {
  to { transform: rotate(360deg); }
}

.textarea-with-button .send-button {
  position: absolute;
  bottom: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background-color: #4CAF50;
  color: white;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

  .textarea-with-button textarea:focus {
    outline: none;
    border-color: #4CAF50;
    box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2);
  }
  
  /* Send button styles removed from App.vue to use style.css */

  .textarea-with-button textarea:disabled {
    background-color: #f5f5f5;
    cursor: not-allowed;
  }

  .input-container button {
    padding: 12px 24px;
    background-color: #2196F3;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 500;
    transition: background-color 0.3s ease;
  }

  .input-container button:hover {
    background-color: #1976D2;
  }

  .input-container button:active {
    background-color: #1565C0;
  }

  .input-container button.cancel-button {
    background-color: #f44336;
    width: 40px;
    padding: 12px;
    font-size: 16px;
    line-height: 1;
  }

  .input-container button.cancel-button:hover {
    background-color: #d32f2f;
  }

/* 美化滚动条 - 默认隐藏，鼠标悬停时显示 */
.process-content::-webkit-scrollbar {
  width: 0;
  position: absolute;
  right: 0;
  transition: width 0.2s ease;
}

.process-content::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.process-content::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.process-content::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* 鼠标悬停时显示滚动条 */
.process-content:hover::-webkit-scrollbar {
  width: 8px;
}

/* 最终结果框滚动条样式 - 默认隐藏，鼠标悬停时显示 */
.result-content::-webkit-scrollbar {
  width: 0;
  position: absolute;
  right: 0;
  transition: width 0.2s ease;
}

.result-content:hover::-webkit-scrollbar {
  width: 8px;
}

.result-content::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.result-content::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.result-content::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .app-container {
    padding: 8px;
    gap: 8px;
  }
  
  .display-container {
    flex-direction: column;
    gap: 15px;
  }
  
  .process-container,
  .result-container {
    min-height: 180px;
  }
  
  .input-container textarea {
    height: 80px;
    font-size: 14px;
  }
  
  /* 响应式登录页面 */
  .login-form {
    padding: 30px 20px;
  }
  
  .login-title {
    font-size: 24px;
  }
  
  /* 响应式顶部导航 */
  .app-header {
    flex-direction: column;
    gap: 10px;
    text-align: center;
  }
  
  .user-info {
    justify-content: center;
  }
}

@media (max-width: 480px) {
  .app-container {
    padding: 10px;
    gap: 10px;
  }
  
  .process-container h3,
  .result-container h3 {
    font-size: 16px;
  }
  
  .input-container {
    flex-direction: column;
  }
  
  .input-container button {
    align-self: flex-end;
    padding: 10px 20px;
  }
  
  /* 小屏幕登录页面 */
  .login-form {
    padding: 20px 15px;
  }
  
  .login-logo svg {
    width: 50px;
    height: 50px;
  }
}
.model-down {
     padding-left: 50px;
     margin-top: 10px;
}

/* Readability overrides for the light workspace theme. */
.app-container { gap: 0; padding: 0; background: var(--tech-bg-dark); }
.main-content { gap: 0; }
.result-container { padding: 0; border: 0; border-radius: 0; background: #ffffff; }
.result-container.processing { animation: none; }
.textarea-with-button { width: 100%; max-width: none; }
.attachment-input { display: none; }
.attachment-button { position: absolute; left: 12px; bottom: 12px; width: 32px; height: 32px; border: 1px solid #d4dbe2; border-radius: 6px; background: #fff; cursor: pointer; }
.attachment-button:disabled { opacity: .5; cursor: not-allowed; }
.attachment-list { position: absolute; left: 52px; right: 12px; top: 8px; display: flex; gap: 6px; overflow: hidden; }
.attachment-chip { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 4px 8px; border-radius: 4px; background: #e8f2ef; color: #176b5b; font-size: 12px; }
.textarea-with-button textarea { height: 86px; border-radius: 8px; border-color: transparent; }
.textarea-with-button textarea:focus { border-color: transparent; box-shadow: none; }
.textarea-with-button .location-button { background: #ffffff; border-color: #d4dbe2; color: #66717f; }
.textarea-with-button .location-button:hover { background: #f1f4f6; color: #176b5b; }
.textarea-with-button .location-button.active { background: #e8f2ef; border-color: #9ebfb7; color: #176b5b; }
.textarea-with-button .send-button { background: #176b5b; color: #ffffff; }
.top-user-section { top: 22px; right: 24px; margin-top: 0; }
.login-container { background: #f3f5f7; }
.attachment-remove { border: 0; background: transparent; color: #64748b; cursor: pointer; margin-left: 4px; padding: 0 2px; font-size: 16px; line-height: 1; }
.attachment-remove:hover { color: #c0392b; }
.session-unread { min-width: 18px; padding: 1px 5px; border-radius: 10px; background: #1f8a70; color: #fff; font-size: 11px; text-align: center; }
.login-form { border: 1px solid #dce2e8; border-radius: 8px; box-shadow: 0 12px 36px rgba(31, 42, 55, .10); }
.login-title { color: #202a35; background: none; -webkit-text-fill-color: currentColor; }
.login-input-group input:focus { border-color: #7da99f; box-shadow: 0 0 0 3px rgba(23, 107, 91, .10); }

@media (max-width: 760px) {
  .app-container { padding: 0; }
  .textarea-with-button textarea { height: 76px; }
  .top-user-section { top: 16px; right: 16px; }
}

.input-container {
  position: relative;
  inset: auto;
  transform: none;
  width: min(760px, calc(100% - 48px));
  max-width: none;
  margin: 0 auto 24px;
  flex: 0 0 auto;
}

.model-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 64px;
  color: #4c5966;
  font-size: 13px;
}

.model-selector select {
  min-width: 150px;
  max-width: 220px;
  padding: 7px 28px 7px 10px;
  border: 1px solid #d4dbe2;
  border-radius: 6px;
  background: #fff;
  color: #202a35;
}

@media (max-width: 640px) {
  .model-selector { margin-right: 48px; }
  .model-selector select { min-width: 120px; max-width: 150px; }
}

.top-user-section {
  position: relative;
  inset: auto;
  flex: 0 0 auto;
  min-height: 64px;
  padding: 10px 24px;
  margin: 0;
  gap: 12px;
  box-sizing: border-box;
}
.model-selector { margin-right: 0; min-width: 0; }
.model-profile-delete, .workspace-delete {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  padding: 0;
  border: 1px solid #e1c7c4;
  border-radius: 5px;
  background: #fff;
  color: #a33d37;
  cursor: pointer;
}
.model-profile-delete:hover:not(:disabled), .workspace-delete:hover:not(:disabled) { background: #fff4f2; }
.model-profile-delete:disabled, .workspace-delete:disabled { opacity: .5; cursor: wait; }
.project-selector { position: relative; }
.project-selector > .workspace-delete { position: absolute; right: 0; bottom: 4px; }
.project-selector select { padding-right: 44px; }
.project-selector > .workspace-create-error { display: block; margin-top: 5px; }
.model-config-button, .mobile-sidebar-toggle {
  min-height: 36px;
  border: 1px solid #d4dbe2;
  border-radius: 6px;
  background: #fff;
  color: #202a35;
  cursor: pointer;
}
.model-config-button { padding: 6px 10px; white-space: nowrap; }
.model-config-panel {
  position: absolute;
  top: calc(100% - 4px);
  right: 24px;
  width: min(340px, calc(100vw - 32px));
  box-sizing: border-box;
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #d4dbe2;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(23, 33, 43, .12);
}
.model-config-panel input, .model-config-panel select, .model-config-panel button {
  min-width: 0;
  min-height: 36px;
  box-sizing: border-box;
}
.main-container { min-width: 0; }
.chat-message-container { padding-top: 12px; }
.toggle-sidebar-btn { right: 6px; width: 28px; height: 28px; }
.sidebar-backdrop { display: none; }
.textarea-with-button .attachment-button,
.textarea-with-button .location-button { width: 32px; height: 32px; min-width: 32px; padding: 0; }
.textarea-with-button .attachment-button { background: #fff; color: #66717f; }
.textarea-with-button .location-button { right: 84px; }
.textarea-with-button .send-button { width: 64px; padding: 0; }
.textarea-with-button textarea { padding-bottom: 48px; }

@media (max-width: 760px) {
  .sidebar-wrapper { position: fixed; inset: 0 auto 0 0; z-index: 301; }
  .sidebar-content.expanded { width: min(272px, calc(100vw - 56px)); overflow-y: auto; }
  .sidebar-backdrop { display: block; position: fixed; inset: 0; z-index: 300; border: 0; background: rgba(23, 33, 43, .25); }
  .top-user-section { padding: 8px 12px; min-height: 56px; gap: 8px; }
  .mobile-sidebar-toggle { width: 36px; flex: 0 0 36px; margin-right: auto; font-size: 20px; }
  .model-selector { gap: 6px; margin: 0; }
  .model-selector label { display: none; }
  .model-selector select { min-width: 0; width: 124px; max-width: 30vw; }
  .model-config-panel { right: 12px; }
  .chat-message-container { padding: 12px 14px 18px; }
  .input-container { width: calc(100% - 28px); margin-bottom: 14px; }
  .textarea-with-button textarea { box-sizing: border-box; }
}
/* Shared layout tracks keep messages and composer on the same reading column. */
.result-container { --reading-width: 780px; }
.top-user-section { inset: auto; min-height: 72px; padding: 12px 24px; border-bottom: 1px solid #e6eaee; }
.workspace-title { flex: 1; min-width: 0; text-align: left; }
.workspace-eyebrow { display: block; font-size: 11px; line-height: 16px; color: #687380; }
.workspace-title h1 { margin: 2px 0 0; font: 600 15px/22px system-ui, sans-serif; color: #26323b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; letter-spacing: 0; }
.model-selector { flex: 0 1 auto; margin: 0; }
.user-avatar-container { flex-shrink: 0; }
.model-config-button, .mobile-sidebar-toggle { display: grid; place-items: center; width: 36px; height: 36px; padding: 0; flex-shrink: 0; }
.toggle-sidebar-btn { display: grid; place-items: center; border-radius: 4px; box-shadow: none; }
.sidebar-section-label { padding: 10px 11px 5px; text-align: left; color: #78838d; font-size: 11px; line-height: 18px; font-weight: 600; }
.tools-section-label { margin-top: 12px; }
.navigation-container { padding-bottom: 14px; }
.nav-icon, .history-icon { flex-shrink: 0; }
.history-icon { color: #84908e; }
.history-page-status { flex-shrink: 0; text-align: center; color: #687380; font-size: 13px; }
.history-page-button { margin: 6px 0; padding: 6px 10px; border: 0; background: transparent; color: #147565; cursor: pointer; font-size: 13px; }
.history-page-button:disabled { opacity: .5; cursor: not-allowed; }
.history-error { display: block; color: #ad3d3d; font-size: 13px; padding: 6px; }
.task-status-panel { width: min(100%, var(--reading-width)); box-sizing: border-box; margin: 0 auto 18px; padding: 12px 14px; border: 1px solid #d7dfdc; border-radius: 6px; background: #f7faf9; }
.task-status-header, .task-status-row, .task-status-actions { display: flex; align-items: center; }
.task-status-header { justify-content: space-between; margin-bottom: 6px; color: #263b36; }
.task-status-row { justify-content: space-between; gap: 16px; padding: 9px 0; border-top: 1px solid #e3e9e7; }
.task-status-copy { display: grid; min-width: 0; gap: 3px; }
.task-status-name { font-size: 13px; font-weight: 600; color: #334b45; }
.task-status-copy small { color: #6b7773; font-size: 11px; }
.task-status-error { color: #a33d37; font-size: 12px; overflow-wrap: anywhere; }
.task-status-actions { flex: 0 0 auto; gap: 6px; }
.task-action-button, .task-refresh-button { min-height: 30px; padding: 4px 9px; border: 1px solid #ccd8d4; border-radius: 4px; background: #fff; color: #28594e; cursor: pointer; font-size: 12px; }
.task-action-button.primary { border-color: #147565; background: #147565; color: #fff; }
.task-action-button:disabled, .task-refresh-button:disabled { opacity: .55; cursor: wait; }
.session-item { border: 0; text-align: left; min-height: 38px; box-sizing: border-box; display: flex; align-items: center; gap: 4px; }
.session-item.selected { background: #eaf1ef; border: 0; box-shadow: none; }
.session-info { min-width: 0; width: 100%; }
.session-preview { text-align: left; flex: 1; min-width: 0; color: #52625e; }
.session-delete-button { flex: 0 0 28px; width: 28px; height: 28px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 4px; background: transparent; color: #8a9693; cursor: pointer; }
.session-delete-button:hover { background: #f8e9e7; color: #ad3d3d; }
.session-delete-button:disabled { opacity: .5; cursor: wait; }
.session-confirm-button, .session-cancel-button { flex: 0 0 auto; min-height: 28px; padding: 3px 7px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.session-confirm-button { border: 1px solid #ad3d3d; background: #ad3d3d; color: #fff; }
.session-cancel-button { border: 1px solid #d4dbe2; background: #fff; color: #52625e; }
.chat-message-container { padding: 28px 24px; scrollbar-gutter: stable both-edges; }
.message-wrapper { width: min(100%, var(--reading-width)); max-width: var(--reading-width); margin-left: auto; margin-right: auto; }
.input-container { width: min(var(--reading-width), calc(100% - 48px)); margin: 0 auto 24px; }
.textarea-with-button { box-sizing: border-box; }
.textarea-with-button textarea { box-sizing: border-box; font-size: 15px; padding: 14px 14px 48px; }
.textarea-with-button .attachment-button, .textarea-with-button .location-button, .textarea-with-button .send-button { display: grid; place-items: center; width: 36px; height: 36px; padding: 0; border-radius: 6px; }
.textarea-with-button .location-button { right: 56px; }
.input-container .textarea-with-button .send-button { min-width: 36px; width: 36px; background: #147565; }
.input-container .textarea-with-button .send-button:hover { background: #0e6254; }
.input-container .textarea-with-button .send-button.cancel-button { background: #bb4141; }
.input-container .textarea-with-button .send-button:disabled { background: #eef1f4; color: #98a1ab; cursor: not-allowed; }
.textarea-with-button .attachment-button { left: 12px; }
.textarea-with-button .attachment-button:hover { background: #edf3f1; color: #147565; }
.attachment-list { position: static; padding: 10px 12px 0; }
@media (max-width: 760px) {
  .top-user-section { min-height: 64px; padding: 10px 14px; gap: 8px; }
  .mobile-sidebar-toggle { margin-right: 0; }
  .workspace-title h1 { font-size: 14px; }
  .model-selector select { width: 90px; max-width: 22vw; padding-left: 6px; }
  .chat-message-container { padding: 22px 14px; scrollbar-gutter: auto; }
  .task-status-row { align-items: flex-start; }
  .task-status-actions { flex-wrap: wrap; justify-content: flex-end; }
  .input-container { width: calc(100% - 28px); margin-bottom: 14px; }
  .brand-copy { display: grid; }
}
</style>
