import{request,post}from'./client.js';
export const getOverview=()=>request('/recruitment/overview');
export const getRecruitments=()=>request('/recruitments');
export const getRecruitment=id=>request('/recruitments/'+id);
export const createRecruitment=data=>post('/recruitments',data);
export const lockRecruitment=id=>post(`/recruitments/${id}/lock`,{});
export const withdrawAssignment=id=>post(`/assignments/${id}/withdraw`,{});
export const getRoster=id=>request(`/plans/${id}/roster`);
