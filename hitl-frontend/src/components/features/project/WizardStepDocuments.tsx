import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocumentDropzone } from './DocumentDropzone';
import { DocumentList } from './DocumentList';
import { Button } from '../../ui/Button';
import { Spinner } from '../../ui/Spinner';
import { useProjectStore } from '../../../stores/projectStore';
import * as ragApi from '../../../api/rag';
import type { UploadedFile } from '../../../api/types';

interface WizardStepDocumentsProps {
  className?: string;
}

export function WizardStepDocuments({ className = '' }: WizardStepDocumentsProps): JSX.Element {
  const { t } = useTranslation();
  const slug = useProjectStore((s) => s.wizardData.slug);
  const gitConfig = useProjectStore((s) => s.wizardData.gitConfig);

  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [vectorizing, setVectorizing] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(true);

  // Git clone state
  const [showGitForm, setShowGitForm] = useState(false);
  const [useProjectCreds, setUseProjectCreds] = useState(true);
  const [gitRepoName, setGitRepoName] = useState('');
  const [gitService, setGitService] = useState('');
  const [gitUrl, setGitUrl] = useState('');
  const [gitLogin, setGitLogin] = useState('');
  const [gitToken, setGitToken] = useState('');
  const [cloning, setCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    if (!slug) return;
    setLoadingFiles(true);
    try {
      const result = await ragApi.listUploads(slug);
      setFiles(result);
    } catch {
      // handled by apiFetch
    } finally {
      setLoadingFiles(false);
    }
  }, [slug]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const handleUpload = useCallback(async (file: File) => {
    if (!slug) return;
    setUploading(true);
    try {
      const result = await ragApi.uploadDocument(slug, file);
      if (result.files_extracted > 0) {
        // Archive extracted — reload full list
        await loadFiles();
      } else {
        setFiles((prev) => [...prev, { name: result.filename, size: result.size, content_type: result.content_type }]);
      }
      if (result.chunks_indexed > 0) {
        setVectorizing(true);
        setTimeout(() => setVectorizing(false), 2000);
      }
    } catch {
      // handled by apiFetch
    } finally {
      setUploading(false);
    }
  }, [slug, loadFiles]);

  const handleDelete = useCallback(async (filename: string) => {
    if (!slug) return;
    try {
      await ragApi.deleteUpload(slug, filename);
      setFiles((prev) => prev.filter((f) => f.name !== filename));
    } catch {
      // handled by apiFetch
    }
  }, [slug]);

  const handleCloneGit = useCallback(async () => {
    if (!slug || !gitRepoName) return;
    setCloning(true);
    setCloneError(null);
    try {
      await ragApi.cloneGitToUploads(slug, {
        repo_name: gitRepoName,
        use_project_creds: useProjectCreds,
        service: useProjectCreds ? undefined : gitService,
        url: useProjectCreds ? undefined : gitUrl,
        login: useProjectCreds ? undefined : gitLogin,
        token: useProjectCreds ? undefined : gitToken,
      });
      await loadFiles();
      setShowGitForm(false);
      setGitRepoName('');
    } catch (err) {
      setCloneError(err instanceof Error ? err.message : String(err));
    } finally {
      setCloning(false);
    }
  }, [slug, gitRepoName, useProjectCreds, gitService, gitUrl, gitLogin, gitToken, loadFiles]);

  const SERVICE_OPTIONS = useMemo(() => [
    { value: 'other', label: t('git.other'), url: '' },
    { value: 'github', label: 'GitHub', url: 'https://github.com' },
    { value: 'gitlab', label: 'GitLab', url: 'https://gitlab.com' },
    { value: 'gitea', label: 'Gitea', url: '' },
    { value: 'forgejo', label: 'Forgejo', url: '' },
    { value: 'bitbucket', label: 'Bitbucket', url: 'https://bitbucket.org' },
  ], [t]);

  const handleServiceChange = useCallback((value: string) => {
    setGitService(value);
    const opt = SERVICE_OPTIONS.find((o) => o.value === value);
    if (opt?.url) setGitUrl(opt.url);
  }, [SERVICE_OPTIONS]);

  const inputClass = 'rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none w-full';

  return (
    <div className={`flex flex-col gap-4 max-w-lg ${className}`}>
      <DocumentDropzone onUpload={(f) => void handleUpload(f)} uploading={uploading} />

      {vectorizing && (
        <div className="flex items-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-xs">{t('documents.vectorizing')}</span>
        </div>
      )}

      {/* Git clone section */}
      {!showGitForm ? (
        <Button variant="secondary" size="sm" onClick={() => setShowGitForm(true)} className="self-start">
          {t('documents.clone_git')}
        </Button>
      ) : (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-secondary p-4">
          <h4 className="text-sm font-semibold text-content-secondary">{t('documents.clone_git')}</h4>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-content-tertiary">{t('documents.git_repo_name')}</span>
            <input
              type="text"
              value={gitRepoName}
              onChange={(e) => setGitRepoName(e.target.value)}
              placeholder="owner/repo"
              className={inputClass}
            />
          </label>

          {gitConfig && (
            <label className="flex items-center gap-2 text-xs text-content-secondary">
              <input
                type="checkbox"
                checked={useProjectCreds}
                onChange={(e) => setUseProjectCreds(e.target.checked)}
              />
              {t('documents.use_project_creds')}
            </label>
          )}

          {(!useProjectCreds || !gitConfig) && (
            <div className="flex flex-col gap-2">
              <select
                value={gitService || 'other'}
                onChange={(e) => handleServiceChange(e.target.value)}
                className={inputClass}
              >
                {SERVICE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <input type="text" value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} placeholder={t('git.url')} className={inputClass} />
              <input type="text" value={gitLogin} onChange={(e) => setGitLogin(e.target.value)} placeholder={t('git.login')} className={inputClass} />
              <input type="password" value={gitToken} onChange={(e) => setGitToken(e.target.value)} placeholder={t('git.token')} className={inputClass} />
            </div>
          )}

          {cloneError && <p className="text-xs text-accent-red">{cloneError}</p>}

          <div className="flex gap-2">
            <Button size="sm" onClick={() => void handleCloneGit()} loading={cloning} disabled={!gitRepoName}>
              {t('documents.clone')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setShowGitForm(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}

      {loadingFiles ? (
        <div className="flex justify-center py-4"><Spinner size="md" /></div>
      ) : (
        <DocumentList files={files} onDelete={(f) => void handleDelete(f)} />
      )}
    </div>
  );
}
